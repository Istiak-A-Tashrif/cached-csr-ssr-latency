<script>
	import { onMount, afterUpdate } from "svelte";
	export let rows;
	export let page;
	export let limit;
	export let respId;
	export let navigate;

	$: id = `data-p${page}-l${limit}`;

	// Harness entry point: marks the action start, then navigates.
	onMount(() => {
		window.__nav = (p, l, aid = "") => {
			performance.mark(`nav-p${p}-l${l}`);
			navigate(p, l, aid);
		};
	});

	// Secondary endpoint: framework commit time of this data (after hydration for SSR).
	let last = "";
	afterUpdate(() => {
		const k = `${id}|${respId}`;
		if (k !== last) {
			last = k;
			(window.__commits ??= []).push({ id, respId, t: performance.now() });
		}
	});
</script>

<!-- key block: a new element per view so visibility is recorded for every render -->
{#key `${id}-${respId}`}
	<table data-view={id} data-resp-id={respId}>
		<tbody>
			{#each rows as r, i (r.id)}
				<tr>
					<td elementtiming={i === 0 ? id : undefined} data-vis={i === 0 ? id : undefined}>{r.name}</td>
					<td>{r.category}</td>
					<td>{r.total_orders}</td>
					<td>{Number(r.avg_rating).toFixed(2)}</td>
					<td>{r.stock}</td>
				</tr>
			{/each}
		</tbody>
	</table>
{/key}
