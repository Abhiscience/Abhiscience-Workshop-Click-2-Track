"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const DESIGNATIONS = [
  { id: "gate_in", label: "Gate Staff", icon: "🚪", color: "#2563eb" },
  { id: "service_advisor", label: "Service Advisor", icon: "📋", color: "#7c3aed" },
  { id: "technician", label: "Technician", icon: "🔧", color: "#b45309" },
  { id: "quality_check", label: "Quality Check", icon: "✅", color: "#16a34a" },
  { id: "washing", label: "Washing", icon: "🚿", color: "#0891b2" },
  { id: "floor_incharge", label: "Floor Incharge", icon: "👷", color: "#dc2626" },
  { id: "gate_out", label: "Gate Out", icon: "🏁", color: "#4b5563" },
];

export default function StaffLoginPage() {
  const [step, setStep] = useState<"designation" | "login">("designation");
  const [designation, setDesignation] = useState<any>(null);
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleDesignationSelect = (d: any) => {
    setDesignation(d);
    setStep("login");
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("username", mobile);
      formData.append("password", password);
      const res = await fetch("/api/auth/login", { method: "POST", body: formData });
      const data = await res.json();
      if (data.access_token) {
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("designation", designation.id);
        localStorage.setItem("designation_label", designation.label);
        localStorage.setItem("designation_icon", designation.icon);
        localStorage.setItem("mobile", mobile);
        router.push("/staff/capture");
      } else {
        setError("Invalid mobile or password");
      }
    } catch (err) {
      setError("Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  if (step === "designation") {
    return (
      <div style={{ minHeight: "100vh", background: "#0f172a", padding: "20px", fontFamily: "sans-serif" }}>
        <div style={{ maxWidth: "420px", margin: "0 auto" }}>
          <div style={{ textAlign: "center", padding: "30px 0 20px" }}>
            <p style={{ fontSize: "40px", marginBottom: "8px" }}>🏭</p>
            <h1 style={{ color: "white", fontSize: "22px", fontWeight: "bold" }}>Workshop Click-2-Track</h1>
            <p style={{ color: "#94a3b8", fontSize: "14px", marginTop: "4px" }}>Select your designation to continue</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginTop: "20px" }}>
            {DESIGNATIONS.map((d) => (
              <button key={d.id} onClick={() => handleDesignationSelect(d)}
                style={{ background: "#1e293b", border: `2px solid ${d.color}`, borderRadius: "12px", padding: "20px 12px", cursor: "pointer", textAlign: "center", transition: "all 0.2s" }}>
                <p style={{ fontSize: "32px", marginBottom: "8px" }}>{d.icon}</p>
                <p style={{ color: "white", fontSize: "13px", fontWeight: "600" }}>{d.label}</p>
              </button>
            ))}
          </div>
          <div style={{ textAlign: "center", marginTop: "24px" }}>
            <a href="/login" style={{ color: "#94a3b8", fontSize: "13px", textDecoration: "none" }}>Admin Login →</a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a", padding: "20px", fontFamily: "sans-serif", display: "flex", alignItems: "center" }}>
      <div style={{ maxWidth: "420px", margin: "0 auto", width: "100%" }}>
        <button onClick={() => setStep("designation")}
          style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "14px", marginBottom: "20px", padding: "0" }}>
          ← Back
        </button>
        <div style={{ background: "#1e293b", borderRadius: "16px", padding: "30px" }}>
          <div style={{ textAlign: "center", marginBottom: "24px" }}>
            <p style={{ fontSize: "48px" }}>{designation?.icon}</p>
            <h2 style={{ color: "white", fontSize: "20px", fontWeight: "bold", marginTop: "8px" }}>{designation?.label}</h2>
            <p style={{ color: "#94a3b8", fontSize: "13px", marginTop: "4px" }}>Enter your credentials</p>
          </div>
          {error && (
            <div style={{ background: "#7f1d1d", borderRadius: "8px", padding: "12px", marginBottom: "16px" }}>
              <p style={{ color: "#fca5a5", fontSize: "14px" }}>{error}</p>
            </div>
          )}
          <form onSubmit={handleLogin}>
            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", color: "#94a3b8", fontSize: "13px", marginBottom: "6px" }}>Mobile Number</label>
              <input type="tel" value={mobile} onChange={e => setMobile(e.target.value)}
                placeholder="0501234567" required
                style={{ width: "100%", padding: "12px", background: "#0f172a", border: "1px solid #334155", borderRadius: "8px", color: "white", fontSize: "16px", boxSizing: "border-box" }} />
            </div>
            <div style={{ marginBottom: "24px" }}>
              <label style={{ display: "block", color: "#94a3b8", fontSize: "13px", marginBottom: "6px" }}>Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder="••••••••" required
                style={{ width: "100%", padding: "12px", background: "#0f172a", border: "1px solid #334155", borderRadius: "8px", color: "white", fontSize: "16px", boxSizing: "border-box" }} />
            </div>
            <button type="submit" disabled={loading}
              style={{ width: "100%", padding: "14px", background: designation?.color || "#2563eb", color: "white", border: "none", borderRadius: "10px", fontSize: "16px", fontWeight: "600", cursor: "pointer" }}>
              {loading ? "Signing in..." : "Sign In →"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
