import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { components } from "../api/types";

export type Field = components["schemas"]["FieldOut"];
export type FieldMeta = components["schemas"]["FieldMeta"];
export type FieldCreate = components["schemas"]["FieldCreate"];
export type FieldPatch = components["schemas"]["FieldPatch"];
export type Entity = FieldCreate["entity"];
export type FieldType = FieldCreate["type"];

export const TYPE_LABELS: Record<FieldType, string> = {
  text: "Short text",
  long_text: "Long text",
  number: "Number",
  money: "Money",
  date: "Date",
  bool: "Yes / no",
  choice: "Choice",
  multi_choice: "Multiple choice",
};

export function useFields(entity: Entity) {
  return useQuery({
    queryKey: ["fields", entity],
    queryFn: ({ signal }) =>
      api<{ items: Field[] }>(`/fields?entity=${entity}`, { signal }).then((r) => r.items),
    retry: false,
  });
}

/** Every change refreshes the field lists and anything that renders custom values. */
export function useFieldMutations() {
  const qc = useQueryClient();
  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["fields"] }),
      qc.invalidateQueries({ queryKey: ["donor"] }),
      qc.invalidateQueries({ queryKey: ["donors"] }),
    ]);
  return {
    create: useMutation({
      mutationFn: (body: FieldCreate) => api<Field>("/fields", { method: "POST", body }),
      onSuccess: refresh,
    }),
    patch: useMutation({
      mutationFn: (v: { id: number; body: FieldPatch }) =>
        api<Field>(`/fields/${v.id}`, { method: "PATCH", body: v.body }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>(`/fields/${id}`, { method: "DELETE" }),
      onSuccess: refresh,
    }),
  };
}
