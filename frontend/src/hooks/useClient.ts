import { useQuery } from "@tanstack/react-query";
import { getClient, type Client } from "../clients";

export function useClientQuery(id: number) {
  return useQuery<Client, Error>({
    queryKey: ["client", id],
    queryFn: () => getClient(id),
    enabled: id > 0,
  });
}
