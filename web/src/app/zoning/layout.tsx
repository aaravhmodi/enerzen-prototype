import type { Metadata } from "next";
import "./zoning.css";

export const metadata: Metadata = {
  title: "Pickering Zoning · EnerZen",
  description: "Find a Pickering lot, see its zoning and overlays on the map, and the by-law pages that govern it.",
};

export default function ZoningLayout({ children }: { children: React.ReactNode }) {
  return children;
}
