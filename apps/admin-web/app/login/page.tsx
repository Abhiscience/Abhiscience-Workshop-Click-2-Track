"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const formData = new FormData();
    formData.append("username", mobile);
    formData.append("password", password);
    const res = await fetch("/api/auth/login", { method: "POST", body: formData });
    const data = await res.json();
    if (data.access_token) {
      localStorage.setItem("token", data.access_token);
      router.push("/analytics");
    } else {
      setError("Invalid mobile or password");
    }
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f9fafb" }}>
      <div style={{ background: "white", padding: "40px", borderRadius: "12px", boxShadow: "0 4px 20px rgba(0,0,0,0.1)", width: "360px" }}>
        <h1 style={{ fontSize: "24px", fontWeight: "bold", marginBottom: "8px" }}>Workshop Click-2-Track</h1>
        <p style={{ color: "#666", marginBottom: "24px" }}>Sign in to your account</p>
        {error && <p style={{ color: "red", marginBottom: "16px" }}>{error}</p>}
        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", marginBottom: "6px", fontWeight: "500" }}>Mobile Number</label>
            <input type="text" value={mobile} onChange={e => setMobile(e.target.value)}
              placeholder="0501234567"
              style={{ width: "100%", padding: "10px", border: "1px solid #ddd", borderRadius: "8px", fontSize: "16px" }} />
          </div>
          <div style={{ marginBottom: "24px" }}>
            <label style={{ display: "block", marginBottom: "6px", fontWeight: "500" }}>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              style={{ width: "100%", padding: "10px", border: "1px solid #ddd", borderRadius: "8px", fontSize: "16px" }} />
          </div>
          <button type="submit"
            style={{ width: "100%", padding: "12px", background: "#2563eb", color: "white", border: "none", borderRadius: "8px", fontSize: "16px", cursor: "pointer" }}>
            Sign In
          </button>
        </form>
      </div>
    </div>
  );
}
