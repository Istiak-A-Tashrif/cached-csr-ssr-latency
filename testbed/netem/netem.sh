#!/bin/sh
# Shape this container's egress toward a peer host.
#   netem.sh set <peer-hostname> <one-way-delay-ms> [rate e.g. 10mbit]
#   netem.sh clear <peer-hostname>
#   netem.sh show <peer-hostname>
# Added RTT on a link = sum of the one-way delays configured at both ends.
# The harness puts RTT/2 on each end so neither direction is double-counted.
set -e
cmd=$1; peer=$2
# An IPv4 literal is used as is (getent would try reverse DNS for it).
case "$peer" in
  *[!0-9.]*) ip=$(getent hosts "$peer" | awk '{print $1}' | head -1) ;;
  *) ip=$peer ;;
esac
[ -n "$ip" ] || { echo "cannot resolve $peer" >&2; exit 1; }
dev=$(ip -o route get "$ip" | sed -n 's/.* dev \([^ ]*\).*/\1/p')
case "$cmd" in
  set)
    delay=$3; rate=$4
    tc qdisc del dev "$dev" root 2>/dev/null || true
    if [ -n "$rate" ]; then
      tc qdisc add dev "$dev" root netem delay "${delay}ms" rate "$rate" limit 100000
    else
      tc qdisc add dev "$dev" root netem delay "${delay}ms" limit 100000
    fi ;;
  clear) tc qdisc del dev "$dev" root 2>/dev/null || true ;;
  show)  tc qdisc show dev "$dev" ;;
  *) echo "usage: $0 set|clear|show peer [delay_ms] [rate]" >&2; exit 2 ;;
esac
echo "$cmd $peer ($ip via $dev) ${3:-} ${4:-}"
