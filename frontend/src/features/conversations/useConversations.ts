import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { conversationApi } from "@/lib/api";
import type { ConversationDetail, ConversationList, ConversationOut } from "@/types/api";

export const conversationKeys = {
  all: ["conversations"] as const,
  list: () => ["conversations", "list"] as const,
  detail: (id: string) => ["conversations", "detail", id] as const,
};

export function useConversationList(enabled = true) {
  return useQuery({ queryKey: conversationKeys.list(), queryFn: ({ signal }) => conversationApi.list(signal), enabled, staleTime: 15_000 });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: conversationKeys.detail(id ?? "none"),
    queryFn: ({ signal }) => conversationApi.get(id as string, signal),
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

export function useConversationMutations() {
  const client = useQueryClient();
  const invalidate = () => client.invalidateQueries({ queryKey: conversationKeys.all });

  const create = useMutation({
    mutationFn: (title?: string | null) => conversationApi.create(title),
    onSuccess: (created) => {
      client.setQueryData<ConversationList>(conversationKeys.list(), (old) =>
        old ? { total: old.total + 1, conversations: [created, ...old.conversations] } : { total: 1, conversations: [created] });
    },
  });
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => conversationApi.rename(id, title),
    onSuccess: (updated: ConversationOut) => {
      client.setQueryData<ConversationList>(conversationKeys.list(), (old) =>
        old ? { ...old, conversations: old.conversations.map((c) => (c.id === updated.id ? updated : c)) } : old);
      client.setQueryData<ConversationDetail>(conversationKeys.detail(updated.id), (old) => (old ? { ...old, title: updated.title } : old));
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => conversationApi.remove(id),
    onSuccess: (_void, id) => {
      client.setQueryData<ConversationList>(conversationKeys.list(), (old) =>
        old ? { total: Math.max(0, old.total - 1), conversations: old.conversations.filter((c) => c.id !== id) } : old);
      client.removeQueries({ queryKey: conversationKeys.detail(id) });
    },
  });
  return { create, rename, remove, invalidate };
}
