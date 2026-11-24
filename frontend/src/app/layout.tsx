import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Jahtaria Travel Services — U.S. Visa Intelligence & Document Automation",
  description:
    "Jamaican U.S. Visa Preparation, Consular Interview Intelligence, Good Standing Risk Engine & Document Automation Platform.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased selection:bg-ja-goldBright selection:text-ja-green">
        {children}
      </body>
    </html>
  );
}
