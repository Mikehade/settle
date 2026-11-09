import type { components } from "./schema";

type Schemas = components["schemas"];

export type User = Schemas["UserResponse"];
export type AccessToken = Schemas["TokenResponse"];
/** A dispute Settle has mediated, as it recorded it. */
export type DisputeRecord = Schemas["DisputeResponse"];
/** A dispute open in PayPal (or a seeded demo one), before Settle has looked at it. */
export type OpenDispute = Schemas["OpenDisputeSummary"];
/** A dispute's case file, assembled without mediating it. */
export type DisputePreview = Schemas["DisputePreviewResponse"];
/** One decision in a dispute's audit trail, with the case file and decision it was made on. */
export type AuditEntry = Schemas["AuditEntryResponse"];
/** A row of the audit list: one decision, without the case file and PayPal's reply. */
export type AuditListItem = Schemas["AuditEntryListItem"];
/** The result of approving or rejecting an escalated recommendation. */
export type ActionResult = Schemas["ActionResultResponse"];
/** A seller's fairness policy: rules for the mediator, and limits checked in code. */
export type Policy = Schemas["PolicyResponse"];
export type PolicyUpdate = Schemas["PolicyUpdateRequest"];
