import {Component, inject, signal} from '@angular/core';
import {MatIconModule} from '@angular/material/icon';
import {ActivatedRoute, Router, RouterLink} from '@angular/router';

import {AuthService} from '../../core/auth.service';
import {
  decodeCandidateAccessPayload,
  resolveCandidateEmail,
  resolveCandidateInvitationToken,
  resolveCandidateJobId,
} from '../../core/candidate-access.util';
import {DataService} from '../../core/data.service';

type CandidateAccessFlow = 'invite' | 'l0_session' | 'invalid';

@Component({
  selector: 'app-candidate-access',
  standalone: true,
  imports: [MatIconModule, RouterLink],
  template: `
    <div class="auth-canvas flex min-h-screen items-center justify-center px-4 py-10">
      <div class="grid w-full max-w-6xl gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section class="page-hero p-8 sm:p-10">
          <span class="brand-chip">
            <mat-icon class="text-[15px]">shield</mat-icon>
            Candidate Gateway
          </span>

          <div class="relative mt-8 space-y-5">
            <div class="flex items-center gap-3">
              <span class="brand-logo-mark"><mat-icon class="text-[20px]">hub</mat-icon></span>
              <div>
                <p class="text-xs font-bold uppercase tracking-[0.24em] text-white/70">TalentOS</p>
                <p class="text-sm text-white/80">Secure candidate progression</p>
              </div>
            </div>

            <div>
              <h1 class="max-w-xl font-['Space_Grotesk'] text-4xl font-bold leading-tight sm:text-5xl">
                {{ flow() === 'l0_session' ? 'Verified access to your live L0 assessment.' : 'Verified access to your interview booking journey.' }}
              </h1>
              <p class="mt-4 max-w-2xl text-sm leading-7 text-white/82 sm:text-base">
                Every candidate link is checked on the server before login so the booking and assessment flows stay tied to the invited email, booked slot, and live session status.
              </p>
            </div>

            <div class="grid gap-3 sm:grid-cols-3">
              <div class="glass-panel p-4">
                <p class="text-xs uppercase tracking-[0.18em] text-white/60">Step 1</p>
                <p class="mt-2 text-sm font-semibold text-white">OTP sign-in</p>
              </div>
              <div class="glass-panel p-4">
                <p class="text-xs uppercase tracking-[0.18em] text-white/60">Step 2</p>
                <p class="mt-2 text-sm font-semibold text-white">Face verification</p>
              </div>
              <div class="glass-panel p-4">
                <p class="text-xs uppercase tracking-[0.18em] text-white/60">Step 3</p>
                <p class="mt-2 text-sm font-semibold text-white">Anti-spoof and assessment</p>
              </div>
            </div>
          </div>
        </section>

        <section class="auth-card max-w-none">
          <div class="space-y-6 p-8 sm:p-10">
            <div>
              <span class="auth-header-kicker">
                <mat-icon class="text-[16px]">verified</mat-icon>
                Link Validation
              </span>
              <h2 class="mt-4 font-['Space_Grotesk'] text-3xl font-bold text-[var(--brand-ink)]">
                {{ validationPending() ? 'Checking your link' : flow() === 'invalid' ? 'Access unavailable' : 'Access approved' }}
              </h2>
              <p class="mt-2 text-sm leading-7 text-[var(--brand-copy-soft)]">
                {{ validationPending()
                  ? 'We are confirming your invite details, booked schedule, and access state with TalentOS.'
                  : flow() === 'invalid'
                    ? 'This candidate link is invalid, expired, or no longer active.'
                    : 'Your access link is valid. Continue with the invited candidate account to proceed.' }}
              </p>
            </div>

            @if (validationPending()) {
              <div class="auth-panel flex items-center gap-3 text-sm text-[var(--brand-copy-soft)]">
                <mat-icon class="animate-spin text-[20px] text-primary-600">progress_activity</mat-icon>
                Secure validation in progress...
              </div>
            } @else if (flow() === 'invalid') {
              <div class="rounded-[1.4rem] border border-red-200 bg-red-50/90 p-5 text-sm text-red-700">
                <p class="font-semibold">Link validation failed</p>
                <p class="mt-2 leading-6">
                  {{ validationMessage() || 'Request a fresh invitation from your recruiter before trying again.' }}
                </p>
              </div>

              <button type="button" routerLink="/auth/candidate/login" class="auth-secondary-button">
                Go to Candidate Login
              </button>
            } @else {
              <div class="auth-panel space-y-4">
                <div class="rounded-[1.2rem] border border-primary-100 bg-white/80 p-4">
                  <p class="text-xs font-bold uppercase tracking-[0.18em] text-primary-700">Validated candidate</p>
                  <p class="mt-2 text-sm font-semibold text-[var(--brand-ink)]">{{ candidateEmail() }}</p>
                  @if (scheduleStatus()) {
                    <p class="mt-1 text-xs text-[var(--brand-copy-soft)]">Current schedule status: {{ scheduleStatus() }}</p>
                  }
                </div>

                @if (flow() === 'invite') {
                  <div class="space-y-2 rounded-[1.2rem] border border-primary-100 bg-primary-50/70 p-4 text-sm text-[var(--brand-copy)]">
                    <p class="font-semibold text-primary-700">Next steps</p>
                    <p>1. Sign in with OTP using the invited email address.</p>
                    <p>2. Complete face registration or verification.</p>
                    <p>3. Book a valid assessment slot and wait for the L0 instructions email.</p>
                  </div>
                } @else {
                  <div class="space-y-2 rounded-[1.2rem] border border-primary-100 bg-primary-50/70 p-4 text-sm text-[var(--brand-copy)]">
                    <p class="font-semibold text-primary-700">L0 assessment sequence</p>
                    <p>1. Sign in with OTP using the invited email address.</p>
                    <p>2. Complete face verification and anti-spoof checks.</p>
                    <p>3. Stay camera-on, remain in the tab, and finish the assessment in one sitting.</p>
                  </div>
                }
              </div>

              <button type="button" (click)="continueToCandidateLogin()" class="auth-primary-button">
                Continue to Candidate Login
              </button>
            }

            <p class="text-center text-xs text-[var(--brand-copy-soft)]">
              Need recruiter support? Contact your hiring team using the invited candidate email.
            </p>
          </div>
        </section>
      </div>
    </div>
  `,
})
export class CandidateAccessComponent {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  authService = inject(AuthService);
  private dataService = inject(DataService);

  flow = signal<CandidateAccessFlow>('invalid');
  candidateEmail = signal<string | null>(null);
  scheduleStatus = signal<string | null>(null);
  validationPending = signal(true);
  validationMessage = signal<string | null>(null);

  private readonly inviteParam = this.route.snapshot.queryParamMap.get('invite');
  private readonly sessionParam = this.route.snapshot.queryParamMap.get('session');

  constructor() {
    void this.initializeAccessContext();
  }

  continueToCandidateLogin(): void {
    this.authService.setPostAuthRedirect(this.postAuthTarget());
    void this.router.navigate(['/auth/candidate/login'], {
      queryParams: this.buildCandidateQueryParams(),
    });
  }

  private async initializeAccessContext(): Promise<void> {
    const invitationToken = resolveCandidateInvitationToken({
      inviteParam: this.inviteParam,
      sessionParam: this.sessionParam,
    });
    const candidateEmail = resolveCandidateEmail({
      inviteParam: this.inviteParam,
      sessionParam: this.sessionParam,
    });
    const payload = decodeCandidateAccessPayload(this.sessionParam ?? this.inviteParam);
    const resolvedFlow: CandidateAccessFlow = this.sessionParam ? 'l0_session' : this.inviteParam ? 'invite' : 'invalid';

    if (!invitationToken || !candidateEmail) {
      this.flow.set('invalid');
      this.validationMessage.set('We could not read the candidate email and invitation token from this link.');
      this.validationPending.set(false);
      return;
    }

    try {
      const validation = await this.authService.validateCandidateAccessLink({
        email: candidateEmail,
        invitationToken,
        flow: resolvedFlow === 'l0_session' ? 'l0_session' : 'invite',
        scheduleId: payload?.schedule_id ?? null,
        slotId: payload?.slot_id ?? null,
      });

      if (!validation.valid) {
        this.flow.set('invalid');
        this.validationMessage.set('This candidate link is invalid, expired, or no longer matches the booked session.');
        return;
      }

      this.flow.set(resolvedFlow);
      this.candidateEmail.set(validation.candidate_email ?? candidateEmail);
      this.scheduleStatus.set(validation.schedule_status);
      this.dataService.setCandidateInvitationToken(invitationToken);
      this.dataService.setCandidateInvitationJobId(validation.job_id ?? resolveCandidateJobId({
        inviteParam: this.inviteParam,
        sessionParam: this.sessionParam,
      }));

      const redirectTarget = this.postAuthTarget();
      this.authService.setPostAuthRedirect(redirectTarget);

      if (this.authService.isAuthenticated()) {
        await this.authService.logout(null);
      }
    } catch (error) {
      this.flow.set('invalid');
      this.validationMessage.set(
        error instanceof Error
          ? error.message
          : 'Unable to validate this candidate access link right now.',
      );
    } finally {
      this.validationPending.set(false);
    }
  }

  private buildCandidateQueryParams(): Record<string, string> {
    const queryParams: Record<string, string> = {next: this.postAuthTarget()};
    if (this.inviteParam) {
      queryParams['invite'] = this.inviteParam;
    }
    if (this.sessionParam) {
      queryParams['session'] = this.sessionParam;
    }
    return queryParams;
  }

  private postAuthTarget(): string {
    return this.flow() === 'l0_session' ? '/assessment' : '/exam';
  }
}
