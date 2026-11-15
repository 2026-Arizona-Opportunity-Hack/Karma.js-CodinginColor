import { useMutation } from "@tanstack/react-query";
import { Search, ShieldCheck, UserPlus } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { components } from "../api/types";
import { MessageTemplates } from "../components/MessageTemplates";
import { QuickNoteSheet } from "../components/QuickNoteSheet";
import { EmptyState, ErrorState, LoadingLedger, PageMasthead } from "../components/Workspace";
import { useMe, type Me } from "../hooks/useAuth";
import {
  useMembersGovernance,
  type Invitation,
  type Member,
  type Scope,
} from "../hooks/useMembersGovernance";
import { calendarDate, initials } from "../lib/format";
import "../components/donor-ownership.css";
import "./settings.css";

function MutationError({ error }: { error: Error | null }) {
  if (!error) return null;
  const status = error instanceof ApiError ? error.status : 0;
  return (
    <div role="alert" className="save-error">
      {status === 401 ? (
        <>
          Your session has ended.{" "}
          <Link to="/login" reloadDocument>
            Sign in again
          </Link>{" "}
          before trying again.
        </>
      ) : status === 403 ? (
        "Your permissions have changed. Current access is being refreshed. Close this sheet to review it."
      ) : status === 501 ? (
        "This action is not available on the server yet. Nothing has been confirmed."
      ) : status === 0 ? (
        "The connection was interrupted. Check the refreshed records before retrying; the request may have reached the server."
      ) : (
        error.message
      )}
    </div>
  );
}

export function SettingsPage() {
  const me = useMe();
  useEffect(() => {
    document.title = "Members & governance · CIC Compass";
  }, []);
  return me.data ? <Settings actor={me.data} /> : null;
}

function Settings({ actor }: { actor: Me }) {
  const { members, governance, change, refresh } = useMembersGovernance(actor.id);
  const id = useId();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [scope, setScope] = useState<Scope | null>(null);
  const [sheet, setSheet] = useState<"invite" | "flatten" | Member | null>(null);
  const [email, setEmail] = useState("");
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [notice, setNotice] = useState("");
  const [copyNotice, setCopyNotice] = useState("");
  const [denied, setDenied] = useState(false);
  const gov = governance.data;
  const fresh = !!gov && !governance.isError && !governance.isFetching;
  const activeAdmin =
    fresh &&
    actor.is_super_admin &&
    gov.mode === "super_admin" &&
    gov.super_admin_state === "active" &&
    gov.super_admin?.id === actor.id;
  const manage = fresh && (gov.mode === "flat" || activeAdmin) && !denied;
  const currentMember =
    typeof sheet === "object" && sheet
      ? members.data?.items.find((m) => m.id === sheet.id)
      : undefined;
  const canDeactivate = (member: Member) =>
    manage &&
    !members.isError &&
    member.is_active &&
    !member.is_super_admin &&
    member.id !== actor.id;
  const invite = useMutation({
    retry: false,
    gcTime: 0,
    mutationFn: async (address: string) => {
      const result = await api<Invitation>("/members/invite", {
        method: "POST",
        body: { email: address } satisfies components["schemas"]["InviteIn"],
      });
      // Keep the one-time link only in this open sheet, never in the query/mutation cache.
      // The dev proxy can report the API origin. Invitations belong to this frontend;
      // preserve the server-issued path while keeping the link on the current app origin.
      setInvitation({
        ...result,
        invite_url: new URL(new URL(result.invite_url).pathname, window.location.origin).href,
      });
    },
    onSettled: refresh,
    onError: (error) => {
      if (error instanceof ApiError && [401, 403].includes(error.status)) setDenied(true);
    },
  });
  const busy = change.isPending || invite.isPending;
  const open = (next: typeof sheet) => {
    change.reset();
    invite.reset();
    setEmail("");
    setInvitation(null);
    setConfirmed(false);
    setCopyNotice("");
    setNotice("");
    setSheet(next);
  };
  const close = () => {
    if (!busy) {
      setSheet(null);
      setInvitation(null);
      invite.reset();
    }
  };
  const commit = (action: Parameters<typeof change.mutate>[0], message: string) => {
    change.mutate(action, {
      onSuccess: () => {
        setSheet(null);
        setScope(null);
        setNotice(message);
      },
      onError: (error) => {
        setConfirmed(false);
        if (error instanceof ApiError && [401, 403].includes(error.status)) setDenied(true);
      },
    });
  };
  const list = members.data?.items ?? [];
  const visible = list.filter(
    (m) =>
      (filter === "all" || (filter === "active") === m.is_active) &&
      `${m.display_name} ${m.email}`.toLowerCase().includes(search.trim().toLowerCase()),
  );
  return (
    <>
      <PageMasthead eyebrow="The stewardship circle / Settings" title="Members & governance">
        A shared mission. Clear responsibilities. Keep the people behind each relationship
        connected.
      </PageMasthead>
      <p>
        <Link to="/settings/api-keys">API keys for other apps</Link>
      </p>
      <p role="status" className="settings-notice">
        {notice}
      </p>
      <section className="governance-charter" aria-labelledby={`${id}-governance`}>
        <div className="charter-heading">
          <ShieldCheck size={23} strokeWidth={1.4} aria-hidden="true" />
          <div>
            <p className="eyebrow">Our working agreement</p>
            <h2 id={`${id}-governance`}>How we share the care</h2>
          </div>
        </div>
        {governance.isError ? (
          <ErrorState error={governance.error} retry={() => void governance.refetch()} />
        ) : !gov ? (
          <LoadingLedger label="Loading governance" />
        ) : (
          <>
            <div className="charter-grid">
              <div>
                <span className="settings-label">Governance</span>
                <h3>{gov.mode === "flat" ? "An equal voice" : "A designated steward"}</h3>
                <p>
                  {gov.mode === "flat"
                    ? "Every active board member can invite members and manage shared settings."
                    : `Shared settings and member management are reserved for ${gov.super_admin?.display_name ?? "the active super admin"}.`}
                </p>
                <span className="status-pill">
                  {gov.mode === "flat" ? "Flat hierarchy" : "Active super admin"}
                </span>
                {gov.super_admin_state === "dormant" && (
                  <p className="secondary-text">
                    The super-admin role is dormant. Its holder participates as a board member.
                  </p>
                )}
              </div>
              <div>
                <span className="settings-label">Donor reassignment</span>
                <h3>
                  {gov.reassign_scope === "anyone"
                    ? "Anyone can lend a hand"
                    : "Each steward, their own"}
                </h3>
                <p>
                  {gov.reassign_scope === "anyone"
                    ? "Members may reassign any donor to an active board member."
                    : "Board members may reassign their own donors. The active super admin may reassign any donor, including those of inactive members."}
                </p>
                {activeAdmin && !denied ? (
                  <form
                    className="scope-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (activeAdmin && !denied && scope && scope !== gov.reassign_scope && !busy)
                        commit(
                          { kind: "scope", scope },
                          "Reassignment scope saved. Donor permissions have been refreshed.",
                        );
                    }}
                  >
                    <label className="note-field" htmlFor={`${id}-scope`}>
                      Who may reassign donors?
                      <select
                        id={`${id}-scope`}
                        value={scope ?? gov.reassign_scope}
                        disabled={busy}
                        onChange={(e) => {
                          setScope(e.target.value as Scope);
                          change.reset();
                        }}
                      >
                        <option value="anyone">Anyone — any donor</option>
                        <option value="own_only">Owners — their own donors</option>
                      </select>
                    </label>
                    <button
                      className="button button-secondary"
                      disabled={busy || !scope || scope === gov.reassign_scope}
                    >
                      {change.isPending ? "Saving…" : "Save scope"}
                    </button>
                  </form>
                ) : (
                  <p className="secondary-text">
                    {gov.mode === "flat"
                      ? "Fixed to anyone in flat mode."
                      : "Only the active super admin can change this scope."}
                  </p>
                )}
              </div>
            </div>
            <footer className="charter-footer">
              <p>
                Super-admin creation, reactivation, transfer, and account deactivation require the
                deployment operator’s setup command.
              </p>
              {activeAdmin && !denied && (
                <button
                  className="text-button danger-text"
                  disabled={busy}
                  onClick={() => open("flatten")}
                >
                  Flatten hierarchy
                </button>
              )}
            </footer>
          </>
        )}
      </section>
      {!sheet && <MutationError error={change.error} />}
      {denied && (
        <p className="quiet-note" role="alert">
          Management actions are paused after an access change. Reload this page after signing in
          with the appropriate account.
        </p>
      )}
      <section className="members-ledger" aria-labelledby={`${id}-members`}>
        <header className="members-heading">
          <div>
            <p className="eyebrow">People behind the mission</p>
            <h2 id={`${id}-members`}>The board directory</h2>
          </div>
          {manage && (
            <button className="button" disabled={busy} onClick={() => open("invite")}>
              <UserPlus size={17} aria-hidden="true" />
              Invite member
            </button>
          )}
        </header>
        {fresh && !manage && !denied && (
          <p className="quiet-note">
            You can view the directory. The active super admin manages invitations and deactivation.
          </p>
        )}
        <div className="members-tools">
          <label className="search-form">
            <Search size={18} aria-hidden="true" />
            <span className="sr-only">Search members</span>
            <input
              type="search"
              placeholder="Find a name or email"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <label className="member-filter">
            Show
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All members</option>
              <option value="active">Active members</option>
              <option value="inactive">Inactive members</option>
            </select>
          </label>
        </div>
        {members.isError ? (
          <ErrorState error={members.error} retry={() => void members.refetch()} />
        ) : members.isPending ? (
          <LoadingLedger label="Loading members" />
        ) : !visible.length ? (
          <EmptyState title={list.length ? "No matching members" : "Your circle starts here"}>
            {list.length
              ? "Try a different name, email, or status."
              : "Members appear here after accepting an invitation."}
          </EmptyState>
        ) : (
          <>
            <p className="members-count" role="status">
              {visible.length} of {list.length} members{members.isFetching ? " · Refreshing…" : ""}
            </p>
            <table className="member-table">
              <caption className="sr-only">Board members, access, and donor ownership</caption>
              <thead>
                <tr>
                  <th scope="col">Member</th>
                  <th scope="col">Access</th>
                  <th scope="col">Relationships</th>
                  <th scope="col">
                    <span className="sr-only">Management</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((m) => (
                  <tr key={m.id}>
                    <th scope="row">
                      <div className="member-identity">
                        <span className="account-mark" aria-hidden="true">
                          {initials(m.display_name)}
                        </span>
                        <div>
                          <strong>
                            {m.display_name}
                            {m.id === actor.id && <span className="member-you"> · You</span>}
                          </strong>
                          <span className="secondary-text">{m.email}</span>
                        </div>
                      </div>
                    </th>
                    <td>
                      <span className={`status-pill ${m.is_active ? "member-active" : ""}`}>
                        {m.is_active ? "Active" : "Inactive"}
                      </span>
                      <span className="secondary-text">
                        {m.is_super_admin
                          ? gov?.super_admin_state === "active"
                            ? "Super admin"
                            : "Dormant super-admin holder"
                          : "Board member"}
                      </span>
                    </td>
                    <td>
                      <strong className="numeric">{m.owned_donor_count}</strong>
                      <span className="secondary-text">
                        {!m.is_active && m.owned_donor_count
                          ? "Needs reassignment"
                          : "Donors in their care"}
                      </span>
                    </td>
                    <td>
                      {canDeactivate(m) && !members.isFetching ? (
                        <button
                          className="text-button danger-text"
                          disabled={busy}
                          aria-label={`Deactivate ${m.display_name}`}
                          onClick={() => open(m)}
                        >
                          Deactivate
                        </button>
                      ) : (
                        <span className="secondary-text">
                          {!m.is_active
                            ? `Deactivated ${m.deactivated_at ? calendarDate(m.deactivated_at) : "previously"}`
                            : m.is_super_admin
                              ? "Protected account"
                              : m.id === actor.id
                                ? "Your account"
                                : "View only"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        <p className="members-footnote">
          Deactivation preserves history. Donors stay assigned until a member with permission
          reassigns them. <Link to="/">View Needs reassignment</Link>
        </p>
      </section>
      {/* GOV-4: in flat mode any member edits templates; otherwise only the active super admin. */}
      {fresh && <MessageTemplates editable={manage} />}
      <QuickNoteSheet
        open={sheet !== null}
        title={
          sheet === "invite"
            ? invitation
              ? "A place in the circle"
              : "Welcome another steward"
            : sheet === "flatten"
              ? "Return to an equal circle"
              : "Pause member access"
        }
        donorName={typeof sheet === "object" && sheet ? sheet.display_name : "Coding in Color"}
        busy={busy}
        onClose={close}
        eyebrow="Members & governance / A considered change"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (busy) return;
            if (sheet === "invite" && manage && !invitation) invite.mutate(email.trim());
            else if (sheet === "flatten" && activeAdmin && !denied && confirmed)
              commit(
                { kind: "flatten" },
                "Hierarchy flattened. Every active board member now has equal governance permissions.",
              );
            else if (
              currentMember &&
              canDeactivate(currentMember) &&
              !members.isFetching &&
              confirmed
            )
              commit(
                { kind: "deactivate", memberId: currentMember.id },
                `${currentMember.display_name} is deactivated. Their donors remain assigned and appear in Needs reassignment.`,
              );
          }}
        >
          <div className="quick-note-body">
            {sheet === "invite" ? (
              invitation ? (
                <>
                  <p role="status">
                    Invitation created for <strong>{invitation.email}</strong>. No email was sent.
                  </p>
                  <p>
                    Share this one-time link privately. It is shown only in this sheet and expires{" "}
                    {new Intl.DateTimeFormat("en-US", {
                      dateStyle: "medium",
                      timeStyle: "short",
                      timeZone: "America/Phoenix",
                    }).format(new Date(invitation.expires_at))}{" "}
                    (Phoenix time).
                  </p>
                  <label className="note-field">
                    Invitation link
                    <input
                      readOnly
                      value={invitation.invite_url}
                      onFocus={(e) => e.target.select()}
                    />
                  </label>
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(invitation.invite_url);
                        setCopyNotice("Link copied. Share it privately with the invited member.");
                      } catch {
                        setCopyNotice(
                          "Copy is unavailable. Select the link above and copy it manually.",
                        );
                      }
                    }}
                  >
                    Copy invitation link
                  </button>
                  <p role="status">{copyNotice}</p>
                  <p className="quiet-note">
                    Copy the link before closing. Invitations are not listed in the directory; the
                    member appears after joining.
                  </p>
                </>
              ) : (
                <>
                  <p>
                    Invite a board member with their individual email. They will choose their own
                    name and password. This invitation grants board-member access.
                  </p>
                  <label className="note-field" htmlFor={`${id}-email`}>
                    Email address
                    <input
                      id={`${id}-email`}
                      type="email"
                      required
                      maxLength={254}
                      autoComplete="email"
                      value={email}
                      disabled={busy || !manage}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </label>
                  <p className="quiet-note">
                    A one-time link expires in 72 hours. You share it privately; Compass does not
                    send an invitation email.
                  </p>
                </>
              )
            ) : sheet === "flatten" ? (
              <>
                <p className="eyebrow danger-text">A change to the whole board</p>
                <p>
                  Your super-admin role will become dormant. All active board members will be able
                  to invite members and manage shared settings, templates, programs, and API keys.
                </p>
                <p>
                  Reassignment scope will become <strong>anyone</strong>. Members will be able to
                  reassign any donor. Your additional super-admin donor access will end.
                </p>
                <p className="quiet-note">
                  This cannot be undone in the app. Only the deployment operator can reactivate the
                  role with the setup command. Your account remains active as a board member.
                </p>
                <label className="ownership-confirm">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    disabled={busy || !activeAdmin || denied}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  <span>I understand these consequences and confirm flattening the hierarchy.</span>
                </label>
              </>
            ) : (
              sheet && (
                <>
                  <p>
                    Deactivate <strong>{sheet.display_name}</strong>? They will be unable to sign in
                    and all their sessions will be revoked immediately.
                  </p>
                  <div className="deactivation-consequence">
                    <span className="settings-label">Care continues</span>
                    <strong className="numeric">
                      {currentMember?.owned_donor_count ?? sheet.owned_donor_count} donors remain
                      assigned
                    </strong>
                    <p>
                      These donors will appear in Needs reassignment. Deactivation does not move or
                      delete relationships, gifts, or history.
                    </p>
                  </div>
                  <p className="quiet-note">
                    There is no reactivation control in this app. Contact the deployment operator
                    before proceeding if access may be needed again.
                  </p>
                  <label className="ownership-confirm">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      disabled={
                        busy ||
                        !currentMember ||
                        !canDeactivate(currentMember) ||
                        members.isFetching
                      }
                      onChange={(e) => setConfirmed(e.target.checked)}
                    />
                    <span>
                      I confirm deactivating {sheet.display_name} and will arrange donor handoffs.
                    </span>
                  </label>
                </>
              )
            )}
            {sheet === "invite" && !invitation && !manage && (
              <p role="alert">Invitations are unavailable with your current access.</p>
            )}
            <MutationError error={sheet === "invite" ? invite.error : change.error} />
          </div>
          <footer className="quick-note-footer">
            {sheet === "invite" ? (
              !invitation && (
                <button className="button" disabled={busy || !manage}>
                  {busy ? "Creating link…" : "Create invitation link"}
                </button>
              )
            ) : (
              <button
                className="button button-danger"
                disabled={
                  busy ||
                  !confirmed ||
                  (sheet === "flatten"
                    ? !activeAdmin || denied
                    : !currentMember || !canDeactivate(currentMember) || members.isFetching)
                }
              >
                {busy
                  ? "Recording change…"
                  : sheet === "flatten"
                    ? "Confirm flatten hierarchy"
                    : "Confirm deactivation"}
              </button>
            )}
            <button type="button" className="text-button" disabled={busy} onClick={close}>
              {invitation ? "Done" : "Cancel"}
            </button>
          </footer>
        </form>
      </QuickNoteSheet>
    </>
  );
}
