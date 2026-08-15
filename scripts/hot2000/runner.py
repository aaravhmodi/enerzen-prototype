"""
Drives the real HOT2000 GUI (v11.13b13) through its native MFC menus via
pywinauto's win32 backend to batch-calculate .h2k house files and read the
results back out of the saved XML.

Why UI automation instead of the ProgramSDK.dll internals: HOT2000 ships a
.NET automation layer (ProgramSDK.dll / HouseFileLibrary.dll) that the GUI
itself is built on, but the classes needed (ProgramManager etc.) are
internal/undocumented and only reachable via reflection — fragile across
HOT2000 versions and outside anything NRCan supports. Driving the actual
menus is slower per run but uses the same interface a human uses, so
there's nothing to reverse-engineer and nothing that can silently drift
from what a person clicking through the GUI would get.

Proven manually (see conversation): open a sample .h2k, Reports->Calculate,
File->Save, then re-read the file — the recalculated
Annual/Consumption/SpaceHeating/@total in the saved XML matched the
Calculation Result dialog exactly (113.069289063 GJ).

Result fields read (all from the first <Results> under <AllResults> — the
one with no houseCode attribute, which is the live/as-modelled result, not
the NBC 9.36 reference-house comparisons like SOC/HOC/HCV/ROC/Reference):
  Annual/Consumption/@total              -> total site energy, GJ/yr
  Annual/Consumption/SpaceHeating/@total -> purchased heating energy, GJ/yr
  Annual/HeatLoss/@total                 -> envelope heat loss, GJ/yr (TEDI numerator)
  Other/@designHeatLossRate              -> peak heating load, W
  Other/@designCoolLossRate              -> peak cooling load, W
  GrossArea/@buildingSurfaceArea         -> m2, for normalizing to per-m2 metrics
"""

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pywinauto import Application
from pywinauto.timings import TimeoutError as PywinautoTimeoutError

HOT2000_DIR = Path("C:/HOT2000 v11.13b13")
HOT2000_EXE = HOT2000_DIR / "HOT2000.exe"
# The MFC main-frame window class name (Afx:<module-base>:...) is derived
# from the process's runtime module address, so it differs on every launch
# and can't be hardcoded — find the frame by title instead.

GJ_TO_KWH = 277.777778


@dataclass
class H2kResult:
    path: str
    total_energy_gj: float
    space_heating_gj: float
    envelope_heat_loss_gj: float
    design_heat_loss_w: float
    design_cool_loss_w: float
    building_surface_area_m2: float

    @property
    def eui_kwh_m2_yr(self) -> float:
        return self.total_energy_gj * GJ_TO_KWH / self.building_surface_area_m2

    @property
    def heating_demand_kwh_yr(self) -> float:
        return self.space_heating_gj * GJ_TO_KWH

    @property
    def tedi_kwh_m2_yr(self) -> float:
        return self.envelope_heat_loss_gj * GJ_TO_KWH / self.building_surface_area_m2

    @property
    def peak_heating_load_w(self) -> float:
        return self.design_heat_loss_w

    @property
    def peak_cooling_load_w(self) -> float:
        return self.design_cool_loss_w


class Hot2000Error(RuntimeError):
    """Raised when a .h2k file fails to open or calculate (validation errors,
    infeasible inputs, etc). The batch loop should catch this per-file and
    keep going rather than aborting the whole run."""


class Hot2000Runner:
    """One long-lived HOT2000 process, fed a sequence of .h2k files.

    Reusing a single process avoids the ~5-10s HOT2000 startup cost per run,
    which matters when sweeping hundreds of design points overnight.
    """

    def __init__(self):
        self.app: Optional[Application] = None
        self.win = None

    def launch(self):
        self.app = Application(backend="win32").start(str(HOT2000_EXE))
        time.sleep(3)

        deadline = time.time() + 15
        frame = None
        while time.time() < deadline and frame is None:
            for w in self.app.windows():
                text = w.window_text()
                if text == "HOT2000" or text.startswith("HOT2000 - ["):
                    frame = w
                    break
            if frame is None:
                time.sleep(0.5)
        if frame is None:
            raise Hot2000Error("HOT2000 main window never appeared")

        self.win = frame
        if self.win.is_minimized():
            self.win.restore()
            time.sleep(0.5)
        self._dismiss_stray_dialogs()

    def _dismiss_stray_dialogs(self, max_dialogs: int = 5):
        """HOT2000 pops modal dialogs for things like 'referenced program
        module could not be loaded' (benign — falls back to General mode)
        or validation errors on Calculate. Clear anything sitting in front
        of the main frame so automation doesn't stall waiting on it."""
        for _ in range(max_dialogs):
            popup = self._find_topmost_dialog()
            if popup is None:
                return
            for btn_title in ("OK", "&OK", "Yes", "&Yes"):
                try:
                    popup.child_window(title=btn_title, class_name="Button").click()
                    time.sleep(0.4)
                    break
                except Exception:
                    continue
            else:
                # Unknown dialog shape — close it rather than hang forever.
                try:
                    popup.close()
                except Exception:
                    return

    def _find_topmost_dialog(self):
        if self.app is None:
            return None
        for w in self.app.windows():
            if w.class_name() == "#32770" and w.is_visible():
                return w
        return None

    def open_file(self, h2k_path: Path, timeout: float = 20.0):
        self.win.set_focus()
        self.win.menu_select("File->Open...")
        open_dlg = self.app.window(title="Open", class_name="#32770")
        open_dlg.wait("visible", timeout=timeout)
        edit = open_dlg.child_window(class_name="Edit", found_index=0)
        edit.set_edit_text(str(h2k_path))
        time.sleep(0.2)
        open_dlg.child_window(title="&Open", class_name="Button").click()

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.5)
            self._dismiss_stray_dialogs()
            if h2k_path.stem in self.win.window_text():
                return

        title = self.win.window_text()
        raise Hot2000Error(f"HOT2000 did not open {h2k_path.name}; window title={title!r}")

    def calculate(self, timeout: float = 60.0) -> None:
        self.win.set_focus()
        self.win.menu_select("Reports->Calculate")

        deadline = time.time() + timeout
        result_dlg = None
        while time.time() < deadline:
            try:
                result_dlg = self.app.window(title="Calculation Result")
                result_dlg.wait("visible", timeout=1)
                break
            except PywinautoTimeoutError:
                error_dlg = self._find_topmost_dialog()
                if error_dlg is not None and error_dlg.window_text() not in ("", "Calculation Result"):
                    text = error_dlg.window_text()
                    self._dismiss_stray_dialogs()
                    raise Hot2000Error(f"Calculate failed: {text}")
                continue
        if result_dlg is None:
            raise Hot2000Error("Calculate timed out with no result dialog")

        result_dlg.child_window(title="OK", class_name="Button").click()
        time.sleep(0.3)

    def save(self):
        self.win.set_focus()
        self.win.menu_select("File->Save")
        time.sleep(1.0)
        self._dismiss_stray_dialogs()

    def close_file(self):
        self.win.set_focus()
        self.win.menu_select("File->Close")
        time.sleep(0.5)
        self._dismiss_stray_dialogs()

    def run_one(self, h2k_path: Path) -> H2kResult:
        """Open, calculate, save, parse, close. Raises Hot2000Error on any
        failure so the batch loop can log it and move to the next file."""
        self.open_file(h2k_path)
        self.calculate()
        self.save()
        result = parse_results(h2k_path)
        self.close_file()
        return result

    def quit(self):
        if self.win is not None:
            try:
                self.win.close()
            except Exception:
                pass
        self.app = None
        self.win = None


def parse_results(h2k_path: Path) -> H2kResult:
    """Read the live (non-reference-house) <Results> block that Calculate+Save
    just wrote into the .h2k XML."""
    tree = ET.parse(h2k_path)
    root = tree.getroot()

    all_results = root.find("AllResults")
    if all_results is None:
        raise Hot2000Error(f"{h2k_path.name}: no <AllResults> — file was never calculated")

    live = None
    for results in all_results.findall("Results"):
        if "houseCode" not in results.attrib:
            live = results
            break
    if live is None:
        raise Hot2000Error(f"{h2k_path.name}: no live <Results> block (only reference-house entries)")

    consumption = live.find("Annual/Consumption")
    space_heating = consumption.find("SpaceHeating")
    heat_loss = live.find("Annual/HeatLoss")
    other = live.find("Other")
    gross_area = other.find("GrossArea") if other is not None else None

    if gross_area is None or other is None:
        raise Hot2000Error(f"{h2k_path.name}: missing Other/GrossArea in results")

    return H2kResult(
        path=str(h2k_path),
        total_energy_gj=float(consumption.attrib["total"]),
        space_heating_gj=float(space_heating.attrib["total"]),
        envelope_heat_loss_gj=float(heat_loss.attrib["total"]),
        design_heat_loss_w=float(other.attrib["designHeatLossRate"]),
        design_cool_loss_w=float(other.attrib["designCoolLossRate"]),
        building_surface_area_m2=float(gross_area.attrib["buildingSurfaceArea"]),
    )


def run_batch(h2k_paths: list[Path], log_fn=print) -> list[tuple[Path, Optional[H2kResult], Optional[str]]]:
    """Runs every file through one HOT2000 session. Returns (path, result-or-None,
    error-or-None) per file so failures don't abort the whole batch."""
    runner = Hot2000Runner()
    runner.launch()
    outcomes = []
    try:
        for i, path in enumerate(h2k_paths):
            log_fn(f"[{i+1}/{len(h2k_paths)}] {path.name}")
            try:
                result = runner.run_one(path)
                outcomes.append((path, result, None))
            except Hot2000Error as e:
                log_fn(f"  FAILED: {e}")
                outcomes.append((path, None, str(e)))
                try:
                    runner.close_file()
                except Exception:
                    pass
    finally:
        runner.quit()
    return outcomes


if __name__ == "__main__":
    sample = HOT2000_DIR / "User" / "3Storey_8Unit.h2k"
    for path, result, error in run_batch([sample]):
        if result:
            print(result)
            print(f"EUI: {result.eui_kwh_m2_yr:.1f} kWh/m2/yr")
            print(f"TEDI: {result.tedi_kwh_m2_yr:.1f} kWh/m2/yr")
            print(f"Peak heating load: {result.peak_heating_load_w:.0f} W")
        else:
            print(f"{path}: {error}")
