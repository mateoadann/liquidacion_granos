import { useQuery } from "@tanstack/react-query";
import { getExtractionHealth, type ExtractionHealth } from "../api/extracciones";

export function useExtractionHealthQuery() {
  return useQuery<ExtractionHealth, Error>({
    queryKey: ["extraction-health"],
    queryFn: () => getExtractionHealth(),
  });
}
