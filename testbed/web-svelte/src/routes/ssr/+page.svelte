<script>
	import { goto } from "$app/navigation";
	import ProductTable from "$lib/ProductTable.svelte";
	export let data;
	// SSR navigation: the server runs `load` for the new view (__data.json request).
	const navigate = (p, l, aid) => goto(`/ssr?page=${p}&limit=${l}&a=${aid}`);
</script>

<ProductTable rows={data.rows} page={data.page} limit={data.limit} respId={data.respId} {navigate} />
