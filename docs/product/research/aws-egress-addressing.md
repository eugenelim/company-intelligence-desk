# AWS egress addressing for a rate-limited publisher — fact check

> Discipline: primary-source fact check (AWS documentation and pricing)

Commissioned 2026-09-11. The worker fetches from a publisher that rate-limits
and blocks by source address, so what address the publisher *sees* is an
architectural decision, not an operational detail.

## The decision in one line

**Do not buy a NAT gateway for reputation that has not been denied.** At this
system's duty cycle it costs roughly **$36/month** versus **~$0.15/month** for a
task-assigned public IP — about 240× — and buys address determinism the
publisher has not asked for. What the publisher *does* ask for is a rate limit,
and that is solved in software, not in networking.

## The two topologies

Fargate in `awsvpc` mode gives every task its own ENI, and all task traffic
flows through it on platform version 1.4.0+.

| | Public subnet, `assignPublicIp: ENABLED` | Private subnet + NAT gateway |
| --- | --- | --- |
| Address the publisher sees | The task ENI's public IPv4, from the regional pool | The NAT gateway's Elastic IP |
| Stable across restarts | **No** | **Yes** |
| Concurrent tasks | **One address each** | One shared address |
| Cost at ~1 hr/day | ~$0.15/mo | ~$36.50/mo |

Fargate-managed ENIs cannot be modified, and no documented mechanism attaches an
Elastic IP to one — *inferred from documentation silence plus the explicit
"cannot modify" statement, not from a stated prohibition.*

**Cost detail.** NAT gateway is **$0.045/hour** plus **$0.045/GB** processed;
public IPv4 addresses have been **$0.005/hour whether attached or idle** since
1 February 2024. So a NAT gateway is ~$32.85/month before data, plus ~$3.65 for
its EIP. The published data-transfer-out rate beyond the 100 GB/month free tier
was **not** confirmed from a primary page and should not be quoted.

## The consequence that actually matters

SEC's limit is *"no more than 10 requests per second, **regardless of the number
of machines used to submit requests**"* — an aggregate obligation on the *user*,
enforced per IP.

Those two facts point in opposite directions, and that is the finding:

- Under the **public-IP** topology, N concurrent tasks present N addresses. The
  publisher's per-IP enforcement would not catch an aggregate breach, but the
  obligation is still breached — and the remedy, when it lands, lands on one
  address arbitrarily.
- Under the **NAT** topology, N tasks share one address, so per-IP enforcement
  and the aggregate obligation coincide — and one misbehaving worker blocks
  every other one.

Either way, **the rate limit must be enforced in the application, centrally,
before egress.** A per-task limiter cannot satisfy an aggregate obligation, and
a network topology cannot enforce one. This is a software requirement that no
choice of subnet resolves.

## Options for a stable, reputable address

| Option | Changes what the publisher sees? | Verdict |
| --- | --- | --- |
| Elastic IP on a NAT gateway | **Yes** — one address for all tasks | The realistic option, if determinism is ever needed |
| BYOIP | **Yes** — your own prefix and reputation | Not available to this project: minimum /24, and the range *"cannot be registered to an individual person"*. Onboarding takes up to a week and AWS vets the range's history |
| Egress-only internet gateway (IPv6) | **No**, for an IPv4-only destination | Free, but IPv4 destinations force DNS64/NAT64 back through a NAT gateway, erasing the saving |
| Global Accelerator | **No** | Its static IPs are inbound entry points. Irrelevant despite the "static IP" framing |
| Self-managed NAT instance + EIP | **Yes** | Cheaper than a NAT gateway; you own patching, HA and connection tracking |

**If a NAT gateway is ever adopted, use a zonal one.** The regional NAT gateway's
*automatic* mode has AWS manage addresses and AZ expansion, which would silently
break any allowlist built on the address. A single zonal gateway is also the only
topology presenting exactly one address — multi-AZ HA means one address per AZ.

## AWS offers nothing for outbound reputation

Worth stating plainly, because the adjacent services sound relevant:

- AWS **publishes** its ranges at `ip-ranges.amazonaws.com/ip-ranges.json`
  explicitly so third parties *"can allow or deny traffic"*. BYOIP ranges are
  deliberately **excluded** from that file — which is the reputation property
  BYOIP actually buys.
- AWS WAF's IP reputation list is **inbound only**. Shield is inbound. The only
  outbound reputation programme AWS runs is for **email** (SES/Pinpoint), not
  HTTP.
- **PrivateLink and VPC endpoints are irrelevant** to a public-internet
  destination; they reach AWS services and partner services, not `sec.gov`.
- **AWS Data Exchange** is a real path to third-party datasets, but only if a
  vendor republishes the data there. It is not a proxy for arbitrary sites.

No AWS documentation was found acknowledging that third parties block EC2
ranges. The support is indirect — publishing the ranges for filtering, and
community guidance pointing at NAT-plus-EIP for third-party allowlists.

## Recommendation for this system

1. **Start on the public-IP topology.** Cheapest, and the observed block was
   self-inflicted rate tripping rather than reputation.
2. **Enforce the 10 req/s limit centrally in the application**, shared across
   workers, since the obligation is aggregate and the cheap topology multiplies
   addresses.
3. **Treat NAT-plus-EIP as an escalation**, adopted only if a correctly-behaved
   client is blocked — at which point a stable address plus a declared contact is
   what lets a publisher attribute traffic and contact you rather than
   blanket-block.

## Known unknowns

- The current per-GB data-transfer-out rate beyond the free tier.
- Whether an Elastic IP can be attached to a Fargate task ENI. Inferred
  impossible; not stated as prohibited.
- Whether an AWS egress address in the production region is accepted by the
  publisher. Testable, and worth testing before the fetch path is relied on.
