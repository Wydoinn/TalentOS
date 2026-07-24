import {Component, inject, signal} from '@angular/core';
import {FormBuilder, ReactiveFormsModule, Validators} from '@angular/forms';
import {ActivatedRoute, RouterLink} from '@angular/router';
import {MatIconModule} from '@angular/material/icon';

import {AuthService} from '../../core/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, MatIconModule],
  template: `
    <div class="auth-canvas min-h-screen px-4 py-6 lg:px-8">
      <div class="mx-auto grid max-w-6xl gap-6 lg:min-h-[calc(100vh-3rem)] lg:grid-cols-[1.02fr_0.98fr] lg:items-center">
        <section class="page-hero flex flex-col justify-between gap-8 p-8 sm:p-10">
          <div>
            <span class="brand-chip">
              <mat-icon class="text-[15px]">admin_panel_settings</mat-icon>
              Manager Login
            </span>

            <div class="mt-6 flex items-center gap-3">
              <span class="brand-logo-mark"><mat-icon class="text-[20px]">hub</mat-icon></span>
              <div>
                <p class="text-xs font-bold uppercase tracking-[0.24em] text-white/70">TalentOS</p>
                <p class="text-sm text-white/80">Hiring workspace</p>
              </div>
            </div>

            <h1 class="mt-7 max-w-xl font-['Space_Grotesk'] text-4xl font-bold leading-tight sm:text-5xl">
              Manage hiring with less clutter.
            </h1>
            <p class="mt-4 max-w-xl text-sm leading-7 text-white/82 sm:text-base">
              Create roles, rank candidates, and run interviews from one secure dashboard.
            </p>
          </div>

          <div class="grid gap-3 sm:grid-cols-3">
            <div class="glass-panel p-4">
              <p class="text-xs font-bold uppercase tracking-[0.18em]">Fast Setup</p>
              <p class="mt-2 text-sm text-white/80">Create new roles and launch hiring in minutes.</p>
            </div>
            <div class="glass-panel p-4">
              <p class="text-xs font-bold uppercase tracking-[0.18em]">Secure</p>
              <p class="mt-2 text-sm text-white/80">OTP, face check, and anti-spoof workflow.</p>
            </div>
            <div class="glass-panel p-4">
              <p class="text-xs font-bold uppercase tracking-[0.18em]">Live Ops</p>
              <p class="mt-2 text-sm text-white/80">Slots, assessments, and decision tracking.</p>
            </div>
          </div>
        </section>

        <section class="auth-card">
          <div class="space-y-6 p-8 sm:p-10">
            <div>
              <span class="auth-header-kicker">
                <mat-icon class="text-[16px]">verified_user</mat-icon>
                Manager Access
              </span>
              <h2 class="mt-4 font-['Space_Grotesk'] text-3xl font-bold text-[var(--brand-ink)]">Welcome back</h2>
              <p class="mt-2 text-sm leading-7 text-[var(--brand-copy-soft)]">
                Sign in with work email OTP.
              </p>
            </div>

            <form [formGroup]="loginForm" (ngSubmit)="onSubmit()" class="space-y-5">
              <div class="auth-panel">
                <label for="email" class="mb-2 block text-sm font-semibold text-[var(--brand-ink)]">Work email</label>
                <div class="relative">
                  <mat-icon class="absolute left-3.5 top-1/2 -translate-y-1/2 text-[18px] text-[var(--brand-copy-soft)]">mail_outline</mat-icon>
                  <input
                    id="email"
                    type="email"
                    formControlName="email"
                    class="w-full rounded-[1rem] border border-[var(--brand-line)] bg-white py-3 pl-10 pr-4 text-sm text-[var(--brand-ink)] outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/15"
                    placeholder="you@company.com"
                    [class.border-red-400]="loginForm.controls.email.invalid && loginForm.controls.email.touched"
                  />
                </div>
                @if (loginForm.controls.email.invalid && loginForm.controls.email.touched) {
                  <p class="mt-2 text-xs text-red-600">Enter a valid manager email.</p>
                }
              </div>

              <button
                type="button"
                (click)="sendOtp()"
                [disabled]="loginForm.controls.email.invalid || authService.loading()"
                class="auth-secondary-button disabled:cursor-not-allowed disabled:opacity-50"
              >
                @if (authService.loading() && !otpSent()) {
                  <span class="inline-flex items-center gap-2"><mat-icon class="animate-spin text-[18px]">progress_activity</mat-icon> Sending OTP...</span>
                } @else {
                  <span class="inline-flex items-center gap-2"><mat-icon class="text-[18px]">{{ otpSent() ? 'refresh' : 'send' }}</mat-icon>{{ otpSent() ? 'Resend OTP' : 'Send OTP' }}</span>
                }
              </button>

              @if (otpSent()) {
                <div class="auth-panel">
                  <label for="otp" class="mb-2 block text-sm font-semibold text-[var(--brand-ink)]">Verification code</label>
                  <div class="relative">
                    <mat-icon class="absolute left-3.5 top-1/2 -translate-y-1/2 text-[18px] text-[var(--brand-copy-soft)]">pin</mat-icon>
                    <input
                      id="otp"
                      type="text"
                      formControlName="otp"
                      inputmode="numeric"
                      maxlength="6"
                      class="w-full rounded-[1rem] border border-[var(--brand-line)] bg-white py-3 pl-10 pr-4 text-sm font-mono tracking-[0.32em] text-[var(--brand-ink)] outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/15"
                      placeholder="123456"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  [disabled]="loginForm.invalid || authService.loading()"
                  class="auth-primary-button disabled:cursor-not-allowed disabled:opacity-50"
                >
                  @if (authService.loading() && otpSent()) {
                    <span class="inline-flex items-center gap-2"><mat-icon class="animate-spin text-[18px]">progress_activity</mat-icon> Verifying...</span>
                  } @else {
                    <span class="inline-flex items-center gap-2">Open Dashboard <mat-icon class="text-[18px]">arrow_forward</mat-icon></span>
                  }
                </button>
              }
            </form>

            @if (infoMessage()) {
              <div class="rounded-[1.2rem] border border-primary-100 bg-primary-50/80 px-4 py-3 text-sm text-[var(--brand-ink)]">
                {{ infoMessage() }}
              </div>
            }

            @if (authService.errorMessage()) {
              <div class="rounded-[1.2rem] border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {{ authService.errorMessage() }}
              </div>
            }

            <p class="text-center text-sm text-[var(--brand-copy-soft)]">
              Need a manager account?
              <a routerLink="/auth/register" class="font-semibold text-primary-700 hover:underline">Register here</a>
            </p>
          </div>
        </section>
      </div>
    </div>
  `,
})
export class LoginComponent {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  authService = inject(AuthService);

  otpSent = signal(false);
  infoMessage = signal<string | null>(null);

  loginForm = this.fb.group({
    email: ['', [Validators.required, Validators.email]],
    otp: [''],
  });

  constructor() {
    const next = this.route.snapshot.queryParamMap.get('next');
    if (next && next.startsWith('/') && !next.startsWith('/auth/')) {
      this.authService.setPostAuthRedirect(next);
    } else {
      this.authService.setPostAuthRedirect(null);
    }
  }

  async sendOtp(): Promise<void> {
    if (this.loginForm.controls.email.invalid) {
      this.loginForm.controls.email.markAsTouched();
      return;
    }
    const email = this.loginForm.controls.email.value?.trim() ?? '';
    try {
      const response = await this.authService.sendLoginOtp(email, 'pm');
      this.otpSent.set(true);
      this.infoMessage.set(response.message);
      this.loginForm.controls.otp.setValidators([Validators.required, Validators.minLength(4)]);
      this.loginForm.controls.otp.updateValueAndValidity();
    } catch {
      this.infoMessage.set(null);
    }
  }

  async onSubmit(): Promise<void> {
    if (!this.otpSent()) {
      await this.sendOtp();
      return;
    }
    if (this.loginForm.invalid) {
      this.loginForm.markAllAsTouched();
      return;
    }
    const email = this.loginForm.controls.email.value?.trim() ?? '';
    const otp = this.loginForm.controls.otp.value?.trim() ?? '';
    try {
      await this.authService.verifyLoginOtp(email, 'pm', otp);
    } catch {}
  }
}
