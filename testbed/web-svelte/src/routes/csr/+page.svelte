<script>
	import { createQuery } from "@tanstack/svelte-query";
	import { derived } from "svelte/store";
	import { page as pageStore } from "$app/stores";
	import { pushState } from "$app/navigation";
	import { env } from "$env/dynamic/public";
	import ProductTable from "$lib/ProductTable.svelte";

	const feCache = env.PUBLIC_FE_CACHE === "on";
	const apiUrl = env.PUBLIC_API_URL;

	// View = shallow-routing state if set, else the URL's query string.
	const view = derived(pageStore, ($p) => ({
		page: $p.state?.page ?? Number($p.url.searchParams.get("page") ?? 1),
		limit: $p.state?.limit ?? Number($p.url.searchParams.get("limit") ?? 25),
	}));

	const query = createQuery(
		derived(view, ({ page, limit }) => ({
			queryKey: ["products", page, limit],
			queryFn: async () => {
				const rid = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
				// Every queryFn call is a TanStack miss; rid links it to the API log.
				(window.__tq ??= []).push({ key: `p${page}-l${limit}`, t: performance.now(), rid });
				const res = await fetch(`${apiUrl}/api/products?page=${page}&limit=${limit}&caller=client&rid=${rid}`);
				if (!res.ok) throw new Error(`HTTP ${res.status}`);
				return res.json();
			},
			staleTime: feCache ? Infinity : 0,
			gcTime: feCache ? Infinity : 0,
		}))
	);

	// CSR navigation: shallow routing, no server round trip.
	const navigate = (p, l, aid) => pushState(`/csr?page=${p}&limit=${l}&a=${aid}`, { page: p, limit: l });
</script>

{#if $query.data}
	<ProductTable rows={$query.data.data} page={$view.page} limit={$view.limit} respId={$query.data.respId} {navigate} />
{:else}
	<p data-loading>Loading…</p>
{/if}
