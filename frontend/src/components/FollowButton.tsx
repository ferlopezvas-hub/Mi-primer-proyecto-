import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { api } from "../lib/api";

interface Follow { id: number; kind: string; target_id: number; name: string; sport: string | null }

export function useFollows() {
  return useQuery({ queryKey: ["follows"], queryFn: () => api<Follow[]>("/me/follows"), staleTime: 60_000 });
}

export function FollowButton({ kind, id, compact }: { kind: "team" | "match" | "competition"; id: number; compact?: boolean }) {
  const qc = useQueryClient();
  const { data } = useFollows();
  const f = data?.find((x) => x.kind === kind && x.target_id === id);
  const m = useMutation({
    mutationFn: () => (f ? api(`/me/follows/${f.id}`, { method: "DELETE" }) : api("/me/follows", { method: "POST", body: { kind, target_id: id } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["follows"] }),
    onError: (e: Error) => alert(e.message),
  });
  const label = f ? "Siguiendo" : "Seguir";
  return (
    <button onClick={(e) => { e.preventDefault(); m.mutate(); }} disabled={m.isPending} aria-pressed={!!f}
      className={compact ? "btn-ghost min-h-[36px] px-3 py-1" : "btn-ghost"} title={f ? "Dejar de seguir" : "Seguir y recibir avisos"}>
      <Star className={`h-4 w-4 ${f ? "fill-current text-warn" : ""}`} />{label}
    </button>
  );
}
