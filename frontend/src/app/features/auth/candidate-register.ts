import {Component, inject, signal} from '@angular/core';
import {FormBuilder, ReactiveFormsModule, Validators} from '@angular/forms';
import {ActivatedRoute, RouterLink} from '@angular/router';
import {MatIconModule} from '@angular/material/icon';

import {AuthService} from '../../core/auth.service';
import {resolveCandidateEmail, resolveCandidateInvitationToken, resolveCandidateJobId} from '../../core/candidate-access.util';
import {DataService} from '../../core/data.service';

@Component({
  selector: 'app-candidate-register',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <div class="auth-canvas flex min-h-screen items-center justify-center px-4 py-10">
      <div class="auth-card">
        <div class="space-y-6 p-8">
          <div class="text-center">
            <span class="auth-header-kicker">
              <mat-icon class="text-[16px]">app_registration</mat-icon>
              Candidate Flow Step 1
            </span>
            <div class="mt-4 flex items-center justify-center gap-2 font-bold tracking-tight text-primary-700">
              <mat-icon class="text-[30px]">person_add</mat-icon>
              <span class="text-2xl">Create Candidate Account</span>
            </div>
            <p class="mt-2 text-sm text-slate-600">Secure OTP signup before face enrollment.</p>
          </div>

          <div class="auth-panel">
            <form [formGroup]="registerForm" (ngSubmit)="onSubmit()" class="space-y-4">
              <div class="grid grid-cols-2 gap-4">
                <div>
                  <label for="firstName" class="mb-1.5 block text-sm font-medium text-slate-700">First Name</label>
                  <input
                    id="firstName"
                    type="text"
                    formControlName="firstName"
                    class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
                    placeholder="John"
                  />
                </div>
                <div>
                  <label for="lastName" class="mb-1.5 block text-sm font-medium text-slate-700">Last Name</label>
                  <input
                    id="lastName"
                    type="text"
                    formControlName="lastName"
                    class="w-full rounded-xl border border-rose-200 bg-white px-4 py-2.5 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
                    placeholder="Doe"
                  />
                </div>
              </div>

              <div>
                <label for="email" class="mb-1.5 block text-sm font-medium text-slate-700">Email</label>
                <div class="relative">
                  <mat-icon class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-[20px]">mail_outline</mat-icon>
                  <input
                    id="email"
                    type="email"
                    formControlName="email"
                    class="w-full rounded-xl border border-rose-200 bg-white py-2.5 pl-10 pr-4 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
                    placeholder="you@example.com"
                  />
                </div>
              </div>

              <button
                type="button"
                (click)="sendOtp()"
                [disabled]="registerForm.controls.email.invalid || registerForm.controls.firstName.invalid || registerForm.controls.lastName.invalid || authService.loading()"
                class="auth-secondary-button disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span class="inline-flex items-center gap-2">
                  {{ otpSent() ? 'Resend OTP' : 'Send OTP' }}
                  <mat-icon class="text-[18px]">send</mat-icon>
                </span>
              </button>

              @if (otpSent()) {
                <div>
                  <label for="otp" class="mb-1.5 block text-sm font-medium text-slate-700">OTP Code</label>
                  <div class="relative">
                    <mat-icon class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-[20px]">pin</mat-icon>
                    <input
                      id="otp"
                      type="text"
                      formControlName="otp"
                      class="w-full rounded-xl border border-rose-200 bg-white py-2.5 pl-10 pr-4 tracking-[0.24em] outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
                      placeholder="123456"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  [disabled]="registerForm.invalid || authService.loading()"
                  class="auth-primary-button disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span class="inline-flex items-center gap-2">
                    {{ authService.loading() ? 'Verifying OTP...' : 'Verify OTP and Continue' }}
                    <mat-icon class="text-[18px]">arrow_forward</mat-icon>
                  </span>
                </button>
              }
            </form>
          </div>

          @if (infoMessage()) {
            <p class="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {{ infoMessage() }}
            </p>
          }

          @if (authService.errorMessage()) {
            <p class="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {{ authService.errorMessage() }}
            </p>
          }

          <p class="text-center text-sm text-slate-600">
            Already have a candidate account?
            <a routerLink="/auth/candidate/login" class="font-semibold text-primary-700 hover:underline">Sign in</a>
          </p>

        </div>
      </div>
    </div>
  `,
})
export class CandidateRegisterComponent {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private dataService = inject(DataService);
  authService = inject(AuthService);

  otpSent = signal(false);
  infoMessage = signal<string | null>(null);

  registerForm = this.fb.group({
    firstName: ['', Validators.required],
    lastName: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    otp: [''],
  });

  constructor() {
    this.initializeAccessContext();
  }

  async sendOtp(): Promise<void> {
    if (
      this.registerForm.controls.email.invalid
      || this.registerForm.controls.firstName.invalid
      || this.registerForm.controls.lastName.invalid
    ) {
      this.registerForm.controls.firstName.markAsTouched();
      this.registerForm.controls.lastName.markAsTouched();
      this.registerForm.controls.email.markAsTouched();
      return;
    }

    const email = this.registerForm.controls.email.value?.trim() ?? '';
    const displayName = this.composeFullName();

    try {
      const response = await this.authService.sendSignupOtp(email, 'candidate', displayName);
      this.otpSent.set(true);
      this.infoMessage.set(response.message);
      this.registerForm.controls.otp.setValidators([Validators.required, Validators.minLength(4)]);
      this.registerForm.controls.otp.updateValueAndValidity();
    } catch {
      this.infoMessage.set(null);
    }
  }

  async onSubmit(): Promise<void> {
    if (!this.otpSent()) {
      await this.sendOtp();
      return;
    }

    if (this.registerForm.invalid) {
      this.registerForm.markAllAsTouched();
      return;
    }

    const email = this.registerForm.controls.email.value?.trim() ?? '';
    const otp = this.registerForm.controls.otp.value?.trim() ?? '';
    const displayName = this.composeFullName();

    try {
      await this.authService.verifySignupOtp(email, 'candidate', otp, displayName);
    } catch {
      // Error message is exposed from AuthService.
    }
  }

  private composeFullName(): string {
    const firstName = this.registerForm.controls.firstName.value?.trim() ?? '';
    const lastName = this.registerForm.controls.lastName.value?.trim() ?? '';
    return `${firstName} ${lastName}`.trim();
  }

  private initializeAccessContext(): void {
    const inviteParam = this.route.snapshot.queryParamMap.get('invite');
    const sessionParam = this.route.snapshot.queryParamMap.get('session');
    const next = this.route.snapshot.queryParamMap.get('next');

    const invitationToken = resolveCandidateInvitationToken({
      inviteParam,
      sessionParam,
    });
    if (invitationToken) {
      this.dataService.setCandidateInvitationToken(invitationToken);
    }

    const jobId = resolveCandidateJobId({
      inviteParam,
      sessionParam,
    });
    this.dataService.setCandidateInvitationJobId(jobId);

    const candidateEmail = resolveCandidateEmail({
      inviteParam,
      sessionParam,
    });
    if (candidateEmail && !this.registerForm.controls.email.value) {
      this.registerForm.controls.email.setValue(candidateEmail);
    }

    const redirectPath = next && next.startsWith('/')
      ? next
      : (sessionParam ? '/assessment' : (inviteParam ? '/exam' : null));
    if (redirectPath) {
      this.authService.setPostAuthRedirect(redirectPath);
    }
  }
}
