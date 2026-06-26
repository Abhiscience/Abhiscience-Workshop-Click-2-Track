"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function StaffCapturePage() {
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [designation, setDesignation] = useState("");
  const [designationLabel, setDesignationLabel] = useState("");
  const [designationIcon, setDesignationIcon] = useState("");
  const [captures, setCaptures] = useState<any[]>([]);
  const [manualPlate, setManualPlate] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    const token = localStorage.getItem("token");
    const d = localStorage.getItem("designation");
    const dl = localStorage.getItem("designation_label");
    const di = localStorage.getItem("designation_icon");
    if (!token || !d) { router.push("/staff"); return; }
    setDesignation(d || "");
    setDesignationLabel(dl || "");
    setDesignationIcon(di || "");
    const saved = localStorage.getItem("captures_log");
    if (saved) setCaptures(JSON.parse(saved));
  }, []);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImage(file);
      setPreview(URL.createObjectURL(file));
      setResult(null);
      setError("");
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
      if (manualPlate) fd.append("manual_plate", manualPlate);
      const res = await fetch("/api/captures", { method: "POST", body: fd });
      const data = await res.json();
      if (data.event_id) {
        setResult(data);
        const log = {
          event_id: data.event_id,
          plate: data.plate_text_normalized || data.plate_text_raw || "N/A",
          designation: designationLabel,
          icon: designationIcon,
          confidence: data.plate_confidence,
          timestamp: new Date().toLocaleString(),
          status: data.match_status,
        };
        const newCaptures = [log, ...captures].slice(0, 20);
        setCaptures(newCaptures);
        localStorage.setItem("captures_log", JSON.stringify(newCaptures));
        setImage(null);
        setPreview(null);
      } else {
        setError("Failed to process. Try again.");
      }
    } catch (err) {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("designation");
    localStorage.removeItem("designation_label");
    localStorage.removeItem("designation_icon");
    router.push("/staff");
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a", fontFamily: "sans-serif" }}>
      {/* Header */}
      <div style={{ background: "#1e293b", padding: "12px 20px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #334155" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "24px" }}>{designationIcon}</span>
          <div>
            <p style={{ color: "white", fontWeight: "600", fontSize: "14px", margin: 0 }}>{designationLabel}</p>
            <p style={{ color: "#94a3b8", fontSize: "11px", margin: 0 }}>Workshop Click-2-Track</p>
          </div>
        </div>
        <button onClick={handleLogout}
          style={{ background: "#334155", border: "none", color: "#94a3b8", padding: "6px 12px", borderRadius: "6px", cursor: "pointer", fontSize: "12px" }}>
          Logout
        </button>
      </div>

      <div style={{ padding: "20px", maxWidth: "480px", margin: "0 auto" }}>
        {/* Camera Upload */}
        <div onClick={() => fileRef.current?.click()}
          style={{ background: "#1e293b", border: "2px dashed #334155", borderRadius: "16px", padding: "30px", textAlign: "center", cursor: "pointer", marginBottom: "16px", minHeight: "220px", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {preview ? (
            <img src={preview} alt="Preview" style={{ maxWidth: "100%", maxHeight: "220px", borderRadius: "8px" }} />
          ) : (
            <div>
              <p style={{ fontSize: "56px", margin: "0 0 12px" }}>📸</p>
              <p style={{ color: "white", fontWeight: "600", fontSize: "16px", margin: "0 0 4px" }}>Tap to capture plate</p>
              <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>Take photo or upload image</p>
            </div>
          )}
        </div>

        <input ref={fileRef} type="file" accept="image/*" capture="environment"
          onChange={handleImageChange} style={{ display: "none" }} />

        {/* Manual Plate Input */}
        <div style={{ marginBottom: "16px" }}>
          <p style={{ color: "#94a3b8", fontSize: "12px", marginBottom: "6px", letterSpacing: "1px" }}>OR ENTER PLATE MANUALLY</p>
          <input
            type="text"
            value={manualPlate}
            onChange={e => setManualPlate(e.target.value.toUpperCase())}
            placeholder="e.g. A 12345 DUBAI"
            style={{ width: "100%", padding: "12px", background: "#0f172a", border: "1px solid #334155", borderRadius: "8px", color: "white", fontSize: "18px", letterSpacing: "3px", textAlign: "center", boxSizing: "border-box" }}
          />
        </div>

        {error && (
          <div style={{ background: "#7f1d1d", borderRadius: "8px", padding: "12px", marginBottom: "12px" }}>
            <p style={{ color: "#fca5a5", fontSize: "14px", margin: 0 }}>{error}</p>
          </div>
        )}

        <button onClick={handleCapture} disabled={(!image && !manualPlate) || loading}
          style={{ width: "100%", padding: "16px", background: (image || manualPlate) && !loading ? "#2563eb" : "#1e293b", color: (image || manualPlate) ? "white" : "#475569", border: "none", borderRadius: "12px", fontSize: "16px", fontWeight: "700", cursor: image ? "pointer" : "not-allowed", marginBottom: "24px", letterSpacing: "0.5px" }}>
          {loading ? "⏳ Reading plate..." : "🔍 Detect Plate"}
        </button>

        {/* Last Result */}
        {result && (
          <div style={{ background: "#052e16", border: "1px solid #16a34a", borderRadius: "12px", padding: "16px", marginBottom: "24px" }}>
            <p style={{ color: "#4ade80", fontWeight: "700", fontSize: "16px", margin: "0 0 12px" }}>✅ Plate Captured!</p>
            <div style={{ display: "grid", gap: "8px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#86efac", fontSize: "13px" }}>Plate:</span>
                <strong style={{ color: "white", fontSize: "18px", letterSpacing: "2px" }}>{result.plate_text_normalized || result.plate_text_raw || "N/A"}</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#86efac", fontSize: "13px" }}>Confidence:</span>
                <span style={{ color: "white", fontSize: "13px" }}>{result.plate_confidence ? (result.plate_confidence * 100).toFixed(1) + "%" : "N/A"}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#86efac", fontSize: "13px" }}>Status:</span>
                <span style={{ color: "#fbbf24", fontSize: "13px" }}>{result.match_status}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#86efac", fontSize: "13px" }}>Event ID:</span>
                <span style={{ color: "white", fontSize: "13px" }}>#{result.event_id}</span>
              </div>
            </div>
          </div>
        )}

        {/* Capture Log */}
        {captures.length > 0 && (
          <div>
            <p style={{ color: "#94a3b8", fontSize: "13px", fontWeight: "600", marginBottom: "12px", letterSpacing: "1px" }}>TODAY'S CAPTURES</p>
            <div style={{ display: "grid", gap: "8px" }}>
              {captures.map((c, i) => (
                <div key={i} style={{ background: "#1e293b", borderRadius: "10px", padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span style={{ fontSize: "20px" }}>{c.icon}</span>
                    <div>
                      <p style={{ color: "white", fontWeight: "700", fontSize: "15px", margin: 0, letterSpacing: "1px" }}>{c.plate}</p>
                      <p style={{ color: "#64748b", fontSize: "11px", margin: 0 }}>{c.designation} · {c.timestamp}</p>
                    </div>
                  </div>
                  <span style={{ color: "#fbbf24", fontSize: "11px", background: "#292524", padding: "2px 8px", borderRadius: "4px" }}>#{c.event_id}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
