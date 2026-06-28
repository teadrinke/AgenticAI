import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Financial Trading Assistant",
  description: "Multi-agent trading research assistant"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

