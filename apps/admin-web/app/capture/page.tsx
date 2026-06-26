"use client";
import { useState, useRef } from "react";

export default function CapturePage() {
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImage(file);
      setPreview(URL.createObjectURL(file));
      setResult(null);
    }
  };

  const handleCapture = async () => {
    if (!image) return;
    setLoading(true);
    setError("");
    try {
      const token = localStorage.getItem("token");
      const fd = new FormData();
      fd.append("image", image);
      fd.append("token", token || "");
      fd.append("stage_id", "1");
      const res = await fetch("/api/captures", { method: "POST", body: fd });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError("Failed to process image");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "40px", fontFamily: "sans-serif", maxWidth: "600px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "24px", fontWeight: "bold", marginBottom: "8px" }}>Plate Capture</h1>
      <p style={{ color: "#666", marginBottom: "24px" }}>Upload a vehicle image to detect the license plate</p>

      <div style={{ border: "2px dashed #ddd", borderRadius: "12px", padding: "40px", textAlign: "center", marginBottom: "20px", cursor: "pointer" }}
        onClick={() => fileRef.current?.click()}>
        {preview ? (
          <img src={preview} alt="Preview" style={{ maxWidth: "100%", maxHeight: "300px", borderRadius: "8px" }} />
        ) : (
          <div>
            <p style={{ fontSize: "48px" }}>📷</p>
            <p style={{ color: "#666" }}>Click to upload or take a photo</p>
          </div>
        )}
      </div>

      <input ref={fileRef} type="file" accept="image/*" capture="environment"
        onChange={handleImageChange} style={{ display: "none" }} />

      {error && <p style={{ color: "red", marginBottom: "16px" }}>{error}</p>}

      <button onClick={handleCapture} disabled={!image || loading}
        style={{ width: "100%", padding: "14px", background: image ? "#2563eb" : "#ccc", color: "white", border: "none", borderRadius: "8px", fontSize: "16px", cursor: image ? "pointer" : "not-allowed", marginBottom: "20px" }}>
        {loading ? "Processing..." : "Detect Plate"}
      </button>

      {result && (
        <div style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: "12px", padding: "20px" }}>
          <h2 style={{ fontSize: "18px", fontWeight: "bold", marginBottom: "12px", color: "#16a34a" }}>✅ Plate Detected!</h2>
          <div style={{ display: "grid", gap: "8px" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#666" }}>Raw Plate:</span>
              <strong>{result.plate_text_raw || "N/A"}</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#666" }}>Normalized:</span>
              <strong>{result.plate_text_normalized || "N/A"}</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#666" }}>Confidence:</span>
              <strong>{result.plate_confidence ? (result.plate_confidence * 100).toFixed(1) + "%" : "N/A"}</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#666" }}>Status:</span>
              <strong>{result.match_status}</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#666" }}>Event ID:</span>
              <strong>#{result.event_id}</strong>
            </div>
          </div>
        </div>
      )}

      <div style={{ marginTop: "20px", display: "flex", gap: "12px" }}>
        <a href="/analytics" style={{ flex: 1, padding: "12px", background: "#f3f4f6", borderRadius: "8px", textAlign: "center", textDecoration: "none", color: "#333" }}>Analytics</a>
        <a href="/live-tracking" style={{ flex: 1, padding: "12px", background: "#f3f4f6", borderRadius: "8px", textAlign: "center", textDecoration: "none", color: "#333" }}>Live Tracking</a>
      </div>
    </div>
  );
}
