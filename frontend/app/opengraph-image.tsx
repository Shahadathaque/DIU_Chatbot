import { ImageResponse } from "next/og";

export const alt = "DIU Admission AI — verified-source admission guidance";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    <div style={{ background: "#f4f8f5", color: "#15231d", display: "flex", flexDirection: "column", height: "100%", justifyContent: "center", padding: "76px", width: "100%" }}>
      <div style={{ color: "#08783f", display: "flex", fontSize: 28, fontWeight: 700, letterSpacing: 2 }}>DIU ADMISSION AI</div>
      <div style={{ display: "flex", fontSize: 68, fontWeight: 700, letterSpacing: -3, lineHeight: 1.08, marginTop: 28, maxWidth: 980 }}>Verified-source admission guidance for Daffodil International University</div>
      <div style={{ color: "#5f6f67", display: "flex", fontSize: 28, marginTop: 34 }}>Programs · tuition · requirements · eligibility · guides</div>
    </div>,
    size,
  );
}
