# WIZ issues by severity

The open and in-progress WIZ issues of the tenant this check reads, each raised by a
Control or a configuration rule, in a node for each severity WIZ gives them: critical,
high, medium, low and informational, and a node of its own for a severity WIZ names
that this package does not. Each node is a band, and each of its lines is a control or
an issue.

## How to read it

{grading} A band the map grades `OK` — `informational`, unless the configuration says
otherwise — lists its issues for information, and nothing waits on them.

{line_note}

The node above the bands stands for the tenant and reads the worst of them. When WIZ
cannot be read it says so on a line of its own: it warns when WIZ is unavailable or the
run's budget runs out, and fails when WIZ refuses the credential or the query, or
answers with something this check cannot read. No band is written on such a run, so
each keeps what it read last.

A band's details link WIZ's own list of the open and in-progress issues of its
severity, and the tenant's node's the whole list. WIZ's list may hold more than the
band: a threat detection, which this check does not read, and an issue of a control in
`ignore_control_ids`. And a run reads one page of issues, the worst first, `first` of
them, so a tenant with more open issues than that is listed in part, from the worst
down.

## When a band holds issues

1. Open the issue from its line. At the default aggregation level each entity on a
   control's line links to its own issue, and at `entity` an issue's line links its
   issue. WIZ shows what it found on the entity and how to remediate it.
2. Fix what WIZ found on the entity. Once WIZ no longer finds it, WIZ resolves the
   issue, and its line is gone at the next run.
3. While somebody works on it, set the issue in progress in WIZ. Its line says
   *in progress* from the next run on, and the band still counts it.
4. Where your team accepts the finding — a risk it takes, or one a compensating
   control covers — ignore the issue in WIZ with its reason, so that the decision
   stays with the issue. To stop listing every issue of one control, add the
   control's id to `ignore_control_ids`, with who decided it and why beside it.

## Its configuration

```yaml
severity_map:              # what a band holding issues grades as
  critical: ERROR
  high: ERROR
  medium: ERROR
  low: WARN
  informational: OK
aggregation_level: id      # id: a line per control; entity: a line per issue
ignore_control_ids:        # the controls whose issues no band lists
  - wc-1                   # accepted risk: who decided, and when
first: 500                 # the issues a run reads, the worst first, 1 to 1000
```

## While you work on it

{pin_note}
