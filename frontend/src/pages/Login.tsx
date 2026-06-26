// src/pages/Login.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Shield, LogIn, AlertTriangle } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate   = useNavigate();
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const handleSubmit = async () => {
    if (!email || !password) {
      setError("Email and password are required");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch {
      setError("Invalid email or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <Shield className="text-blue-400" size={32} />
          <span className="text-2xl font-bold text-white tracking-wide">ZeroRespond</span>
        </div>

        {/* Card */}
        <div className="bg-surface-800 rounded-xl border border-surface-700 p-8">
          <h2 className="text-lg font-semibold text-white mb-1">Sign in</h2>
          <p className="text-sm text-slate-400 mb-6">
            AI-Enhanced Incident Response Platform
          </p>

          {error && (
            <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20
                            rounded-lg p-3 mb-4 text-sm text-red-400">
              <AlertTriangle size={14} className="shrink-0" />
              {error}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder="responder@hospital.in"
                className="w-full bg-surface-700 border border-surface-600 text-slate-200
                           text-sm rounded-lg px-3 py-2.5 focus:outline-none
                           focus:border-blue-500 placeholder-slate-600"
              />
            </div>

            <div>
              <label className="text-xs text-slate-400 mb-1 block">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                placeholder="••••••••"
                className="w-full bg-surface-700 border border-surface-600 text-slate-200
                           text-sm rounded-lg px-3 py-2.5 focus:outline-none
                           focus:border-blue-500"
              />
            </div>

            <button
              onClick={handleSubmit}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2
                         bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium
                         rounded-lg py-2.5 transition-colors disabled:opacity-50 mt-2"
            >
              <LogIn size={15} />
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </div>
        </div>

        <p className="text-center text-xs text-slate-600 mt-6">
          DPDP Act 2023 Compliant · Data stays on-premises
        </p>
      </div>
    </div>
  );
}