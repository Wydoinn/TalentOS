export interface CandidateAccessPayload {
  flow?: string;
  invitation_token?: string;
  candidate_email?: string;
  job_id?: string;
  schedule_id?: string;
  slot_id?: string;
}

interface CandidateAccessParams {
  inviteParam: string | null;
  sessionParam: string | null;
}

function normalizeBase64Url(value: string): string {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/');
  const padding = (4 - (base64.length % 4)) % 4;
  return `${base64}${'='.repeat(padding)}`;
}

function decodeBase64Url(value: string): string | null {
  try {
    if (typeof atob !== 'function') {
      return null;
    }
    return atob(normalizeBase64Url(value));
  } catch {
    return null;
  }
}

function isLikelyRawToken(value: string | null): value is string {
  if (!value) {
    return false;
  }
  return /^[A-Za-z0-9_-]{20,}$/.test(value);
}

export function decodeCandidateAccessPayload(encoded: string | null | undefined): CandidateAccessPayload | null {
  if (!encoded) {
    return null;
  }

  const decoded = decodeBase64Url(encoded);
  if (!decoded) {
    return null;
  }

  try {
    const parsed = JSON.parse(decoded) as CandidateAccessPayload;
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function resolveCandidateInvitationToken(params: CandidateAccessParams): string | null {
  const invitePayload = decodeCandidateAccessPayload(params.inviteParam);
  if (invitePayload?.invitation_token) {
    return invitePayload.invitation_token;
  }

  const sessionPayload = decodeCandidateAccessPayload(params.sessionParam);
  if (sessionPayload?.invitation_token) {
    return sessionPayload.invitation_token;
  }

  if (isLikelyRawToken(params.inviteParam)) {
    return params.inviteParam;
  }

  return null;
}

export function resolveCandidateEmail(params: CandidateAccessParams): string | null {
  const invitePayload = decodeCandidateAccessPayload(params.inviteParam);
  if (invitePayload?.candidate_email) {
    return invitePayload.candidate_email;
  }

  const sessionPayload = decodeCandidateAccessPayload(params.sessionParam);
  if (sessionPayload?.candidate_email) {
    return sessionPayload.candidate_email;
  }

  return null;
}

export function resolveCandidateJobId(params: CandidateAccessParams): string | null {
  const invitePayload = decodeCandidateAccessPayload(params.inviteParam);
  if (invitePayload?.job_id) {
    return invitePayload.job_id;
  }

  const sessionPayload = decodeCandidateAccessPayload(params.sessionParam);
  if (sessionPayload?.job_id) {
    return sessionPayload.job_id;
  }

  return null;
}
