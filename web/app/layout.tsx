export const metadata = { title: "resumaker", description: "ATS resume tailoring dashboard" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#0b0d12", color: "#e6e8ee" }}>
        <main style={{ maxWidth: 900, margin: "0 auto", padding: "2rem 1.5rem" }}>{children}</main>
      </body>
    </html>
  );
}
