import type { Metadata } from "next";
import { Atkinson_Hyperlegible } from "next/font/google";
import "./globals.css";

const font = Atkinson_Hyperlegible({ weight: ["400", "700"], subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "MzansiHealthChain",
  description: "Patient-controlled access to health records, with every access on the record.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={font.className}>{children}</body>
    </html>
  );
}
