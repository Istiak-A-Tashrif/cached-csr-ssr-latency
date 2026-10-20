<script>
	import { QueryClient, QueryClientProvider } from "@tanstack/svelte-query";
	// Background refetch triggers off: only staleTime/gcTime decide cache use (as in the Next.js app).
	const client = new QueryClient({
		defaultOptions: { queries: { refetchOnWindowFocus: false, refetchOnReconnect: false, retry: false } },
	});
</script>

<QueryClientProvider {client}><slot /></QueryClientProvider>
