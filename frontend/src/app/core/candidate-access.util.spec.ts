import {describe, expect, it} from 'vitest';

import {
  decodeCandidateAccessPayload,
  resolveCandidateEmail,
  resolveCandidateJobId,
  resolveCandidateInvitationToken,
} from './candidate-access.util';

function encodePayload(payload: Record<string, string>): string {
  return btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

describe('candidate access util', () => {
  it('decodes invite payloads', () => {
    const encoded = encodePayload({
      flow: 'invite',
      invitation_token: 'token-abc',
      candidate_email: 'candidate@example.com',
      job_id: 'job-1',
    });

    expect(decodeCandidateAccessPayload(encoded)).toEqual({
      flow: 'invite',
      invitation_token: 'token-abc',
      candidate_email: 'candidate@example.com',
      job_id: 'job-1',
    });
  });

  it('returns null for invalid payloads', () => {
    expect(decodeCandidateAccessPayload('not-base64')).toBeNull();
  });

  it('resolves invitation token from invite payload first', () => {
    const inviteParam = encodePayload({
      flow: 'invite',
      invitation_token: 'invite-token',
      candidate_email: 'candidate@example.com',
      job_id: 'job-1',
    });

    const sessionParam = encodePayload({
      flow: 'l0_session',
      invitation_token: 'session-token',
      candidate_email: 'candidate@example.com',
      job_id: 'job-1',
      schedule_id: 'sched-1',
      slot_id: 'slot-1',
    });

    expect(resolveCandidateInvitationToken({inviteParam, sessionParam})).toBe('invite-token');
  });

  it('falls back to session payload token when invite payload is missing', () => {
    const sessionParam = encodePayload({
      flow: 'l0_session',
      invitation_token: 'session-token',
      candidate_email: 'candidate@example.com',
      job_id: 'job-1',
      schedule_id: 'sched-1',
      slot_id: 'slot-1',
    });

    expect(resolveCandidateInvitationToken({inviteParam: null, sessionParam})).toBe('session-token');
  });

  it('supports raw invitation token fallback', () => {
    expect(
      resolveCandidateInvitationToken({
        inviteParam: 'A1234567890_invitation_token_raw',
        sessionParam: null,
      }),
    ).toBe('A1234567890_invitation_token_raw');
  });

  it('resolves candidate email from encoded payload', () => {
    const inviteParam = encodePayload({
      flow: 'invite',
      invitation_token: 'invite-token',
      candidate_email: 'candidate@example.com',
      job_id: 'job-1',
    });

    expect(resolveCandidateEmail({inviteParam, sessionParam: null})).toBe('candidate@example.com');
  });

  it('resolves candidate job id from invite payload', () => {
    const inviteParam = encodePayload({
      flow: 'invite',
      invitation_token: 'invite-token',
      candidate_email: 'candidate@example.com',
      job_id: 'job-42',
    });

    expect(resolveCandidateJobId({inviteParam, sessionParam: null})).toBe('job-42');
  });

  it('falls back to session payload job id when invite payload is missing', () => {
    const sessionParam = encodePayload({
      flow: 'l0_session',
      invitation_token: 'session-token',
      candidate_email: 'candidate@example.com',
      job_id: 'job-77',
      schedule_id: 'sched-1',
      slot_id: 'slot-1',
    });

    expect(resolveCandidateJobId({inviteParam: null, sessionParam})).toBe('job-77');
  });
});
