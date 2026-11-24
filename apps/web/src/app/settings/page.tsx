"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, KeyRound, Loader2 } from "lucide-react";
import { api, type AiStatus } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

const KIND_LABELS: Record<string, string> = {
  plan: "AI edit plans",
  help: "Help chat replies",
  image: "B-roll images",
  video: "B-roll video (seconds)",
  voiceover: "Voiceover (characters)",
  music: "Music (seconds)",
  sfx: "Sound effects",
};

export default function SettingsPage() {
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [xaiKey, setXaiKey] = useState("");
  const [elKey, setElKey] = useState("");
  const [claudeKey, setClaudeKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => api.aiStatus().then(setStatus).catch((e) => setError(String(e.message ?? e))), []);
  useEffect(() => {
    load();
  }, [load]);

  const save = async (
    keys: { xai_api_key?: string; elevenlabs_api_key?: string; anthropic_api_key?: string },
    note: string,
  ) => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.saveAiKeys(keys);
      setXaiKey("");
      setElKey("");
      setClaudeKey("");
      await load();
      setMessage(note);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  };

  const credits = status?.elevenlabs.credits;
  const usage = status?.usage;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">AI settings</h1>
        <p className="mt-1 text-sm text-muted">
          Making clips needs no keys. Add a key only for the extras you want — each one is billed to your own
          account with that provider.
        </p>
      </div>

      {error && <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p>}
      {message && (
        <p className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
          <CheckCircle2 className="h-4 w-4" />
          {message}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-primary" />
            API keys
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {(
            [
              [
                "Anthropic (Claude) API key",
                "anthropic",
                claudeKey,
                setClaudeKey,
                "sk-ant-…",
                "anthropic_api_key",
                "Powers the Help chat and plans AI edits. Get it at console.anthropic.com → API keys.",
              ],
              [
                "Grok (xAI) API key",
                "xai",
                xaiKey,
                setXaiKey,
                "xai-…",
                "xai_api_key",
                "Generates B-roll images and video. Get it at console.x.ai → API keys.",
              ],
              [
                "ElevenLabs API key",
                "elevenlabs",
                elKey,
                setElKey,
                "sk_…",
                "elevenlabs_api_key",
                "Generates voiceover, music and sound effects. Get it at elevenlabs.io → Developers → API keys.",
              ],
            ] as const
          ).map(([label, provider, value, setter, placeholder, field, help]) => {
            const info = status?.[provider];
            return (
              <div key={provider}>
                <div className="mb-1.5 flex items-center justify-between">
                  <Label className="mb-0">{label}</Label>
                  {info &&
                    (info.configured ? (
                      <Badge tone="success">
                        Connected {info.key_hint} · {info.key_source === "env" ? "from .env" : "saved"}
                      </Badge>
                    ) : (
                      <Badge tone="muted">Not set</Badge>
                    ))}
                </div>
                <div className="flex gap-2">
                  <Input
                    type="password"
                    autoComplete="off"
                    value={value}
                    onChange={(e) => setter(e.target.value)}
                    aria-label={label}
                    placeholder={info?.configured ? "Paste a new key to replace it" : placeholder}
                  />
                  <Button disabled={saving || !value.trim()} onClick={() => save({ [field]: value }, `${label} saved.`)}>
                    {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    Save
                  </Button>
                  {info?.key_source === "saved" && (
                    <Button variant="danger" disabled={saving} onClick={() => save({ [field]: "" }, `${label} removed.`)}>
                      Remove
                    </Button>
                  )}
                </div>
                <p className="mt-1.5 text-xs text-muted">{help}</p>
              </div>
            );
          })}
          <p className="text-xs text-muted">
            Keys are stored on the API server only (in its data folder) and are never sent back to the browser. You can
            also set <code>ANTHROPIC_API_KEY</code>, <code>XAI_API_KEY</code> and <code>ELEVENLABS_API_KEY</code> in <code>services/api/.env</code>.
          </p>
          {status?.elevenlabs.error && <p className="text-xs text-danger">{status.elevenlabs.error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Credits &amp; usage</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div>
            <div className="mb-1.5 flex items-center justify-between text-sm">
              <span className="font-semibold">ElevenLabs credits</span>
              <span className="text-muted">
                {credits
                  ? `${credits.remaining.toLocaleString()} left of ${credits.limit.toLocaleString()}${credits.tier ? ` · ${credits.tier}` : ""}`
                  : "Add a key to see your balance"}
              </span>
            </div>
            {credits && credits.limit > 0 && <Progress value={(credits.used / credits.limit) * 100} />}
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between text-sm">
              <span className="font-semibold">Grok spend (estimated)</span>
              <span className="text-muted">
                ~${(usage?.xai_est_usd ?? 0).toFixed(2)}
                {usage && usage.budget_usd > 0 ? ` of $${usage.budget_usd.toFixed(2)} budget` : " · no budget cap"}
              </span>
            </div>
            {usage && usage.budget_usd > 0 && <Progress value={(usage.xai_est_usd / usage.budget_usd) * 100} />}
            {status && (
              <p className="mt-1.5 text-xs text-muted">
                Estimated from the rates configured on the server (${status.rates.image_usd.toFixed(2)} per image, $
                {status.rates.video_usd_per_sec.toFixed(2)} per second of video) — not your real xAI bill. Set{" "}
                <code>AI_BUDGET_USD</code> to stop generating once the estimate reaches a limit.
              </p>
            )}
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="font-semibold">Claude spend (estimated)</span>
            <span className="text-muted">~${(usage?.anthropic_est_usd ?? 0).toFixed(2)} · from token counts</span>
          </div>

          {usage && usage.items.length > 0 && (
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="py-1.5 font-semibold">Generated</th>
                  <th className="py-1.5 font-semibold">Provider</th>
                  <th className="py-1.5 text-right font-semibold">Calls</th>
                  <th className="py-1.5 text-right font-semibold">Units</th>
                  <th className="py-1.5 text-right font-semibold">Est. cost</th>
                </tr>
              </thead>
              <tbody>
                {usage.items.map((i) => (
                  <tr key={`${i.provider}-${i.kind}`} className="border-t border-border">
                    <td className="py-1.5">{KIND_LABELS[i.kind] ?? i.kind}</td>
                    <td className="py-1.5 text-muted">
                      {i.provider === "xai" ? "Grok" : i.provider === "anthropic" ? "Claude" : "ElevenLabs"}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">{i.count}</td>
                    <td className="py-1.5 text-right tabular-nums">{i.units.toLocaleString()}</td>
                    <td className="py-1.5 text-right tabular-nums">
                      {i.provider === "elevenlabs" ? "—" : `$${i.est_cost_usd.toFixed(2)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {status && (
            <p className="text-xs text-muted">
              Models: {status.anthropic.model} · {status.xai.text_model} · {status.xai.image_model} · {status.xai.video_model} ·{" "}
              {status.elevenlabs.tts_model}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
