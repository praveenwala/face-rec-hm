# Feature Specification: Front Door Person Identification

**Feature Branch**: `001-front-door-person-identification`  
**Created**: 2026-09-09  
**Status**: Draft  
**Input**: User description: "Identify people seen by the Ring Front Door camera as known or unknown, map known identities to household relationship categories such as Family, Friend, or Neighbor, and surface the result in Home Assistant without disrupting existing security automations."

## Clarifications

### Session 2026-09-09

- Q: Should a static photo, screen, or other non-live representation of a face be prevented from producing a "Known" recognition result (anti-spoofing), or is that out of scope for this feature? → A: Require it — a non-live face representation MUST NOT be sufficient evidence for a Known match; it must be treated as Unknown/insufficient confidence. No specific liveness technique is prescribed at the spec level.
- Q: When multiple people (any mix of known/unknown) appear together in one Front Door event, how should the notification behave? → A: A single notification lists every person identified in that event (e.g., "Chandra (Family) and an Unknown person detected at Front Door"), following the existing rate-limit/dedup policy rather than generating one notification per person.
- Q: What should the default notification deduplication/cooldown window be (FR-016/SC-007 require rate-limiting but didn't set a concrete default)? → A: At most one notification per identified person (or per Unknown) within a rolling 5-minute window at the Front Door.
- Q: Can two enrolled identities share the same display name (e.g., two people both named "John")? → A: No — the Identity Library MUST enforce a unique identity name per enrolled person; duplicate real names must be disambiguated (e.g., "John S.") at enrollment time.

## User Scenarios & Testing

### User Story 1 - Detect and Report a Person at the Front Door (Priority: P1)

As a homeowner, I want the system to recognize when a person is present at the Front Door and report the event even when the person's identity cannot be determined, so that I continue receiving useful security awareness.

**Why this priority**: Person detection is the foundational security capability. Identity enrichment is useful only after reliable person detection exists.

**Independent Test**: A person who is not enrolled approaches the Front Door. The system reports a person event and identifies the person as Unknown without requiring any known-face data.

**Acceptance Scenarios**:

1. **Given** the Front Door camera is available, **When** a person enters the monitored area, **Then** the system records a person-detection event.
2. **Given** a person is detected but no reliable identity match exists, **When** the event is processed, **Then** the identity result is `Unknown`.
3. **Given** non-person motion occurs, **When** the event is processed, **Then** no identity result is produced.
4. **Given** identity processing is unavailable, **When** a person is detected, **Then** the base person-detection event remains available.

---

### User Story 2 - Identify an Enrolled Known Person (Priority: P1)

As a homeowner, I want a detected person to be matched to an intentionally enrolled identity when the match is sufficiently reliable, so that I can know who is at the Front Door.

**Why this priority**: Known-person recognition is the primary value beyond ordinary camera motion alerts.

**Independent Test**: Enroll one known person using approved reference images, have that person approach the Front Door, and verify that the system returns the enrolled identity under normal viewing conditions.

**Acceptance Scenarios**:

1. **Given** a person has been intentionally enrolled, **When** that person is detected with a sufficiently clear face and the match meets the configured confidence policy, **Then** the system reports the enrolled identity.
2. **Given** a known person is detected but the visible face is too weak, partial, dark, blurred, or otherwise unreliable, **When** the confidence policy is not met, **Then** the result is `Unknown`.
3. **Given** an unenrolled person resembles an enrolled person, **When** the match is not sufficiently reliable, **Then** the system must not assign the enrolled identity.

---

### User Story 3 - Classify Known People by Relationship (Priority: P2)

As a homeowner, I want each known person to have an explicit relationship category such as Family, Friend, Neighbor, or Other Known, so that notifications provide useful context.

**Why this priority**: Relationship context improves usefulness, but it depends on identity recognition working first.

**Independent Test**: Assign an enrolled identity to a relationship category, generate a successful recognition, and verify that both the person's name and assigned category are available in the resulting event.

**Acceptance Scenarios**:

1. **Given** a known identity has an assigned relationship category, **When** that person is recognized, **Then** the result includes both the identity and the configured category.
2. **Given** a known identity has no relationship category, **When** that person is recognized, **Then** the system reports the identity without inventing a category.
3. **Given** a person is not recognized, **When** the event is processed, **Then** the system must not infer Family, Friend, Neighbor, or any other relationship from appearance.

---

### User Story 4 - Receive a Useful Mobile Notification (Priority: P2)

As a homeowner, I want Home Assistant to notify my phone when a person is detected at the Front Door, including the known identity and relationship when available, so that I can quickly understand who is there.

**Why this priority**: Recognition has little practical value unless its result is delivered in a useful household workflow.

**Independent Test**: Generate one known-person event and one unknown-person event and verify that each produces the expected mobile notification.

**Acceptance Scenarios**:

1. **Given** a known person is recognized, **When** the event reaches Home Assistant, **Then** a notification identifies the known person and relationship category when one is configured.
2. **Given** an unknown person is detected, **When** the event reaches Home Assistant, **Then** the notification clearly states that an unknown person was detected.
3. **Given** repeated detections occur within a short period, **When** notifications are generated, **Then** the system limits duplicate alerts according to the configured notification policy.
4. **Given** the identity subsystem is unavailable, **When** a person event is still available, **Then** the user can still receive a generic person-detected notification.
5. **Given** two or more people (any mix of known and unknown) appear in the same Front Door event, **When** the notification is generated, **Then** a single notification lists every identified person from that event rather than one notification per person.

---

### User Story 5 - Preserve Existing Home Security Behavior During Failures (Priority: P1)

As a homeowner, I want existing Home Assistant security automations to continue working if the person-identification subsystem fails, so that adding AI does not make the house less reliable.

**Why this priority**: The new capability must enhance security rather than become a dependency for existing doorbell and motion functionality.

**Independent Test**: Disable the person-identification subsystem and verify that existing doorbell and motion notifications remain functional.

**Acceptance Scenarios**:

1. **Given** person-identification processing is offline, **When** the doorbell is pressed, **Then** the existing doorbell notification continues to work.
2. **Given** person-identification processing is offline, **When** the existing motion event occurs, **Then** the existing motion automation continues to work.
3. **Given** the identification subsystem restarts, **When** it becomes available again, **Then** Home Assistant resumes receiving enriched person events without requiring the base security automations to be rebuilt.

---

### User Story 6 - Manage the Known-Person Library Safely (Priority: P3)

As a homeowner, I want to add, refine, or remove known identities intentionally, so that recognition data stays accurate and under household control.

**Why this priority**: Ongoing management is required for long-term accuracy but is not needed to prove the initial MVP.

**Independent Test**: Add one identity, update its approved reference images, then remove the identity and verify that it is no longer recognized as known.

**Acceptance Scenarios**:

1. **Given** a new person is intentionally enrolled, **When** enrollment completes, **Then** the identity becomes eligible for recognition.
2. **Given** an enrolled person's reference data is updated, **When** future events are processed, **Then** the updated reference set is used.
3. **Given** an enrolled identity is removed, **When** that person appears again, **Then** the system no longer reports that person as the removed identity.
4. **Given** a new face appears in camera footage, **When** no enrollment action has been taken, **Then** the system must not silently create a named identity.

---

## Edge Cases

- A person appears with only the back or side of the head visible.
- A face is partially covered by a hat, mask, glasses, package, hand, or clothing.
- Two or more people appear at the Front Door at the same time (resolved: reported as one notification listing every identified person — see FR-030).
- A known person and an unknown person appear together (resolved: covered by the same multi-person notification rule — see FR-030).
- A child or person has materially changed appearance since enrollment.
- Lighting is very dark, strongly backlit, overexposed, or affected by rain.
- The camera stream is temporarily unavailable.
- A valid person event arrives after a long delay and is stale.
- The same person triggers multiple events within a short interval.
- A relationship mapping is missing, duplicated, or changed after enrollment.
- Identity processing returns no result even though a person event exists.
- An unavailable value is received for a camera, event, or identity field.
- The household network or identity subsystem restarts while an event is being processed.
- The system sees a photo, screen, reflection, or other non-live representation of a face (resolved: MUST NOT be treated as sufficient for a Known match — see FR-029).
- A recognition result is close to the confidence boundary.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST detect when a person is present in the Front Door camera event stream before attempting identity recognition.
- **FR-002**: The system MUST create a person event for a valid person detection even when identity recognition cannot produce a known match.
- **FR-003**: The system MUST support explicit enrollment of known identities.
- **FR-004**: The system MUST attempt to match a usable detected face only against intentionally enrolled known identities.
- **FR-005**: The system MUST return `Unknown` when no enrolled identity satisfies the configured confidence policy.
- **FR-006**: The system MUST prefer `Unknown` over assigning a low-confidence or ambiguous known identity.
- **FR-007**: The system MUST NOT infer a person's relationship category from appearance.
- **FR-008**: The system MUST allow a known identity to be explicitly mapped to a household relationship category.
- **FR-009**: The initial supported relationship categories MUST include Family, Friend, Neighbor, and Other Known.
- **FR-010**: The system MUST preserve the identity name separately from the relationship category.
- **FR-011**: The system MUST make the final person result available to Home Assistant.
- **FR-012**: The final result MUST distinguish at minimum between a known identity and an unknown person.
- **FR-013**: The system MUST enable Home Assistant to generate a mobile notification for a person event.
- **FR-014**: A known-person notification MUST include the recognized name and, when configured, the relationship category.
- **FR-015**: An unknown-person notification MUST clearly state that the person is unknown.
- **FR-016**: Repeated events MUST be eligible for deduplication or rate limiting so that a single episode does not create excessive notifications. The default policy MUST be at most one notification per identified person (or per Unknown) within a rolling 5-minute window at the Front Door; this window MUST be configurable.
- **FR-017**: Failure of identity recognition MUST NOT suppress the underlying person-detection event.
- **FR-018**: Failure of the person-identification subsystem MUST NOT disable existing doorbell or motion automations.
- **FR-019**: The system MUST distinguish unavailable/stale data from valid values and from a genuine Unknown-person recognition result.
- **FR-020**: The system MUST allow known identities to be removed.
- **FR-021**: Removal of a known identity MUST prevent future events from reporting that removed identity.
- **FR-022**: New camera faces MUST NOT automatically become named identities without explicit enrollment.
- **FR-023**: The first release MUST support the Front Door camera as the sole required camera.
- **FR-024**: The feature design MUST permit later expansion to additional cameras without changing the identity and relationship concepts.
- **FR-025**: The initial feature MUST be informational only and MUST NOT use facial recognition alone to unlock doors, open the garage, disarm security, or perform another physical-access action.
- **FR-026**: The system MUST preserve enough event context for the homeowner to validate whether a recognition result was reasonable.
- **FR-027**: The homeowner MUST be able to refine approved reference data for an enrolled identity.
- **FR-028**: Identity and relationship information MUST remain under household control and MUST NOT be publicly exposed by default.
- **FR-029**: A static photo, screen, reflection, or other non-live representation of a face MUST NOT be sufficient evidence for a `Known` recognition result; such cases MUST resolve to `Unknown` under the confidence policy.
- **FR-030**: When two or more people (any mix of known and unknown identities) are detected in the same Front Door event, the system MUST produce a single notification that lists every identified person from that event rather than a separate notification per person.
- **FR-031**: The system MUST enforce a unique identity name per enrolled person in the Identity Library; enrollment of a duplicate name MUST be rejected or require disambiguation.

### Key Entities

- **Person Detection Event**: A security event indicating that a person was detected at the Front Door. Includes event time, camera/location, processing status, and reference to event evidence when available.
- **Known Identity**: A person intentionally enrolled by the homeowner. Includes a stable, unique identity name and approved recognition reference data.
- **Recognition Result**: The outcome of identity processing for a detected person. Includes Known or Unknown status, matched identity when applicable, and confidence/quality information needed to apply the recognition policy.
- **Relationship Category**: User-maintained contextual classification for a known identity. Initial categories are Family, Friend, Neighbor, and Other Known.
- **Notification Event**: The user-facing alert produced from a person detection and its optional identity enrichment.
- **Camera Source**: The monitored entrance camera associated with the event. The initial required source is Front Door.
- **Identity Library**: The homeowner-controlled collection of intentionally enrolled identities and their approved reference data.

## Success Criteria

### Measurable Outcomes

- **SC-001**: In 10 consecutive normal-condition walk-up tests, the system reports a person event for at least 9 of the 10 approaches.
- **SC-002**: In a test set containing at least 10 appearances of an unenrolled person, the system reports that person as `Unknown` in all cases rather than assigning a known identity.
- **SC-003**: For each enrolled test person, at least 8 of 10 clear, normal-condition Front Door appearances produce the correct known identity after enrollment has been tuned.
- **SC-004**: During low-quality face tests such as partial occlusion, darkness, or blur, the system does not knowingly force a known identity when the configured confidence policy is not satisfied.
- **SC-005**: A recognized known-person event produces a mobile notification containing the correct identity and configured relationship category within 15 seconds of the enriched event becoming available to Home Assistant under normal local-network conditions.
- **SC-006**: An unknown-person event produces a mobile notification explicitly identifying the person as unknown within 15 seconds of the event becoming available to Home Assistant under normal local-network conditions.
- **SC-007**: Repeated detections of the same person within a 5-minute window produce no more than one notification for that person, under the default notification rate-limit policy.
- **SC-008**: When the person-identification subsystem is intentionally stopped for a failure-isolation test, 100% of existing doorbell and motion automation tests continue to pass.
- **SC-009**: A removed identity is not reported as that identity in any subsequent validation test.
- **SC-010**: The system can add one additional camera source later without changing the meaning or structure of Known Identity, Recognition Result, or Relationship Category.
- **SC-011**: No acceptance test requires facial recognition to control a door lock, garage door, alarm disarm action, or other physical-access mechanism.
- **SC-012**: For every reported identity result used during acceptance testing, the homeowner can determine which camera event produced it and whether the result was Known, Unknown, unavailable, or failed.
- **SC-013**: In a test set presenting a printed photo or on-screen image of an enrolled person's face to the Front Door camera, the system reports `Unknown` in 100% of those attempts rather than the enrolled identity.
- **SC-014**: In a test set of at least 5 multi-person Front Door events (any mix of known/unknown people), each event produces exactly one notification listing every identified person rather than multiple separate notifications.

## Assumptions

- The existing Home Assistant instance, Ring devices, and mobile notification path remain available during this feature work.
- The household intentionally chooses which people may be enrolled.
- The initial scope is one camera: Front Door.
- `Unknown` is an acceptable and preferred outcome when identity confidence is insufficient.
- Relationship categories are maintained explicitly by the homeowner and are not learned from appearance.
- Existing doorbell and motion automations remain independent of this feature.
- The feature is intended for household awareness and notification, not autonomous physical access.
- Testing will use cooperative household participants and approved reference images.
- Expansion to additional cameras is a later feature unless required to prove extensibility.
- Detailed technology choices, runtime hosting, container configuration, video transport, model selection, and dependency versions belong in the implementation plan rather than this specification.

## Dependencies

- A working Front Door camera event/video source is available to the project.
- Home Assistant can receive enriched person results from the identification subsystem.
- A mobile notification destination is already configured in Home Assistant.
- The project constitution remains authoritative for privacy, safety, local-first processing, failure isolation, and explicit enrollment.
- Implementation MUST NOT begin until the pre-development environment/tooling validation gate in [pre-development-validation.md](./pre-development-validation.md) has passed (or explicitly deferred, for the face-recognition hardware check).
