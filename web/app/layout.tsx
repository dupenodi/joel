import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "joel",
  description: "Your company's memory, self-hosted.",
  icons: {
    icon: "/brand-kit/favicons/favicon.svg",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      <body className="min-h-full antialiased">{children}</body>
    </html>
  );
}
