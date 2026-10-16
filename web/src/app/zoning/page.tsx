import { redirect } from "next/navigation";

type Props = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ZoningRedirect({ searchParams }: Props) {
  const params = await searchParams;
  const first = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] : value;
  const latitude = Number(first(params.lat));
  const longitude = Number(first(params.lng));
  if (!first(params.lat) || !first(params.lng) || !Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    redirect("/");
  }
  const workspace = new URLSearchParams({ lot: `${latitude},${longitude}` });
  redirect(`/?${workspace.toString()}`);
}
