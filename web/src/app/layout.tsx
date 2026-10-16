import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const futura = localFont({
  src: "../../public/brand/futura-medium.ttf",
  variable: "--font-enerzen",
  display: "swap",
});

export const metadata: Metadata = {
  title: "EnerZen Performance Engine",
  description: "Optimize envelope, energy, carbon, and site fit for Ontario housing.",
  icons: { icon: "/brand/enerzen-symbol.svg" },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${futura.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
