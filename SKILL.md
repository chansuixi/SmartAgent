---
name: Reentrancy
tags: [checks-effects-interactions, external-call, callback, mutex]
description: 
  Reentrancy occurs when a contract transfers control to an untrusted external
  entity (via call/callback) before completing critical state updates, enabling
  the attacker to reenter one or more functions and violate state invariants.
---

patterns:
  - id: ETH-DIRECT
    desc: Reentry via payable call/value transfer (call/send/transfer)
  - id: TOKEN-CALLBACK
    desc: Reentry via token hooks/callbacks (e.g., ERC777) or malicious token contracts
  - id: CROSS-FUNCTION
    desc: Reenter a different public/external function sharing mutable state
  - id: READ-ONLY
    desc: Reentry that manipulates assumptions during external interactions (oracle/DEX state)
  - id: CROSS-CONTRACT
    desc: Reentry path spans multiple contracts/modules

impact:
  - Draining ETH/tokens via repeated withdrawals or transfers
  - Breaking accounting invariants (balances, shares, debts)
  - Unauthorized repeated execution of privileged logic

preconditions:
  - External call transfers control to attacker-controlled code (directly or indirectly)
  - Critical state update occurs after the external call OR invariant assumes “no reentry”
  - Reentry entrypoint exists (fallback/receive/other public/external function)

sinks:
  eth_control_transfer:
    - trigger: ".call{value: V}(DATA)"
    - trigger: "send(V)"
    - trigger: "transfer(V)"
  generic_control_transfer:
    - trigger: "call(DATA)"
    - trigger: "delegatecall(DATA)"
    - triggern: "functionCall(...) / low-level wrappers"
  token_related:
    - trigger: "IERC20(token).transfer(...) / transferFrom(...)"
    - trigger: "ERC777 send / tokensReceived hook patterns"

effects_to_protect:
  - balances[msg.sender] / user shares / debt positions
  - ownership / role changes
  - global accounting totals (totalSupply, totalAssets, pool reserves)
  - “claimed/refunded/withdrawn” flags

workflow:
  - step: Locate candidate sinks (control transfer)
    action:
      - Enumerate external calls in public/external functions
      - Mark calls to addresses derived from msg.sender/user input/registry/token address
    evidence_required: [function, call_expression, callee_address_origin, line_range]

  - step: Identify critical state effects around sinks
    action:
      - Extract state writes before/after the sink
      - Identify whether protected variables are updated after the sink
      - Track whether checks rely on stale state pre-sink
    evidence_required: [state_writes_before, state_writes_after, protected_var_hits]

  - step: Check reentry reachability
    action:
      - Determine if callee can execute attacker code (EOA? contract? unknown address => assume contract)
      - Identify reentry entrypoints (fallback/receive/other public functions)
      - Check if same state can be mutated during reentry (cross-function)
    evidence_required: [callee_is_untrusted, reentry_targets, shared_state]

  - step: Evaluate exploitability (reduce false positives)
    exploitability_checks:
      - attacker_controls_callee: true/false
      - state_updated_after_call: true/false
      - repeatable_gain: ETH|token|privilege|none
      - guard_present_and_effective: true/false
      - call_in_loop: true/false
      - token_hook_possible: true/false
    decision: >
      Report as exploitable if attacker_controls_callee && state_updated_after_call &&
      (repeatable_gain != none) && !guard_present_and_effective.

  - step: Produce minimal exploit trace
    action:
      - Draft a 3–6 step trace: deposit -> trigger -> reenter -> observe invariant break -> profit
      - Include which function is reentered and which state variable is abused
    evidence_required: [exploit_trace, abused_state_vars]

false_positive_filters:
  - External call occurs only after all protected state updates and no dependent checks follow
  - Callee is trusted/immutable and not attacker-controlled (hardcode/known safe module)
  - Function is nonReentrant AND cannot be bypassed by cross-function entrypoints
  - External call is to a view/pure-like context with no invariant assumptions (rare)

tool_hooks:
  slither:
    detectors: [reentrancy-eth, reentrancy-no-eth]
    extract: [call_sites, state_writes, function_visibility, modifiers]
  mythril:
    focus:
      - paths with CALL/CALLCODE/DELEGATECALL
      - storage write after call along same path
    output: [path_constraints, pc_trace]

report_template:
  fields:
    - pattern
    - vulnerable_functions
    - call_sites
    - protected_state_vars
    - why_exploitable
    - minimal_exploit_trace
    - recommended_fix

remediation:
  - checks_effects_interactions: Update state before any external call; do checks first
  - reentrancy_guard: Use a well-scoped mutex (e.g., OpenZeppelin ReentrancyGuard)
  - pull_over_push: Prefer pull payments over direct sends
  - minimize_external_calls: Avoid external interactions in sensitive flows; isolate them
  - token_safety: Treat tokens as untrusted; consider callback/hook behaviors

examples:
  vulnerable:
    - file: examples/reentrancy/eth_withdraw_vuln.sol
      subtype: ETH-DIRECT
      desc: External call before balance decrement enables repeated withdraw
    - file: examples/reentrancy/cross_function_vuln.sol
      subtype: CROSS-FUNCTION
      desc: Reenter different function sharing accounting state
    - file: examples/reentrancy/token_callback_vuln.sol
      subtype: TOKEN-CALLBACK
      desc: Token hook reenters during transfer
  fixed:
    - file: examples/reentrancy/eth_withdraw_cei.sol
      desc: CEI pattern; state updated before call
    - file: examples/reentrancy/guarded.sol
      desc: nonReentrant used correctly; shared entrypoints protected
  false_positive:
    - file: examples/reentrancy/safe_external_call.sol
      desc: External call after all effects; no invariant-dependent logic follows
