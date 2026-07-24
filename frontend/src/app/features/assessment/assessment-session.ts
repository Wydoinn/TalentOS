import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnDestroy, OnInit, ViewChild, computed, inject, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

import {
  type AntiSpoofAnalysis,
  type AntiSpoofChallenge,
  type AssessmentSpeechTranscript,
  type AntiSpoofStatus,
  type AssessmentResult,
  DataService,
  type AssessmentQuestion,
} from '../../core/data.service';

type AssessmentPhase = 'idle' | 'anti_spoof' | 'questions';
type ProctorSeverity = 'INFO' | 'WARNING' | 'CRITICAL';
type WarningDialog = {
  id: number;
  title: string;
  message: string;
};

@Component({
  selector: 'app-assessment-session',
  standalone: true,
  imports: [MatIconModule, CommonModule],
  template: `
    <div class="page-shell animate-in">
      <section class="page-hero p-7 sm:p-8">
        <span class="brand-chip">
          <mat-icon class="text-[15px]">verified_user</mat-icon>
          Candidate Assessment
        </span>
        <h1 class="mt-5 font-['Space_Grotesk'] text-3xl font-bold text-white">L0 Assessment Session</h1>
        <p class="mt-3 max-w-3xl text-sm leading-7 text-white/82">
          OTP login, face verification, anti-spoof validation and real-time browser proctoring all stay active through the assessment flow.
        </p>
      </section>

      @if (assessmentResult()) {
        <section class="surface-card p-8 text-center">
          <div class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[rgba(166,37,104,0.10)] text-[var(--brand-berry)]">
            <mat-icon class="text-[32px]">{{ terminatedSession() ? 'gpp_bad' : 'check_circle' }}</mat-icon>
          </div>
          <h2 class="text-2xl font-bold text-[var(--brand-ink)]">
            {{ terminatedSession() ? 'Assessment Terminated' : 'Assessment Submitted' }}
          </h2>
          <p class="soft-note mt-2">{{ assessmentResult()?.summary }}</p>
          <p class="mt-4 text-lg font-semibold text-[var(--brand-berry)]">Decision: {{ assessmentResult()?.decision }}</p>
          @if (showAssessmentScore()) {
            <p class="mt-2 text-base font-semibold text-[var(--brand-ink)]">Score: {{ assessmentResult()?.overallScore | number:'1.0-0' }}%</p>
          }
          @if (terminationReason()) {
            <p class="mt-3 text-sm font-medium text-[#b42318]">{{ terminationReason() }}</p>
          }
        </section>
      } @else if (assessmentPhase() === 'anti_spoof') {
        <section class="rounded-3xl border border-rose-100 bg-white p-6 shadow-sm shadow-rose-100/70">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="text-xl font-semibold text-slate-900">Anti-Spoof Liveness Verification</h2>
              <p class="mt-1 text-sm text-slate-600">
                Complete this security step to unlock the L0 assessment questions.
              </p>
            </div>
            <span class="rounded-full bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700">
              Session: {{ antiSpoofSessionId() || 'pending' }}
            </span>
          </div>

          <div class="mt-4 grid gap-2 text-xs sm:grid-cols-3">
            <div
              class="rounded-xl border px-3 py-2 text-center font-semibold"
              [class.border-rose-200]="!antiSpoofChallenge()"
              [class.bg-rose-50]="!antiSpoofChallenge()"
              [class.text-rose-700]="!antiSpoofChallenge()"
              [class.border-primary-200]="!!antiSpoofChallenge()"
              [class.bg-primary-50]="!!antiSpoofChallenge()"
              [class.text-primary-700]="!!antiSpoofChallenge()"
            >
              1. Challenge Ready
            </div>
            <div
              class="rounded-xl border px-3 py-2 text-center font-semibold"
              [class.border-rose-200]="!recordedVideoFile()"
              [class.bg-rose-50]="!recordedVideoFile()"
              [class.text-rose-700]="!recordedVideoFile()"
              [class.border-primary-200]="!!recordedVideoFile()"
              [class.bg-primary-50]="!!recordedVideoFile()"
              [class.text-primary-700]="!!recordedVideoFile()"
            >
              2. Clip Recorded
            </div>
            <div
              class="rounded-xl border px-3 py-2 text-center font-semibold"
              [class.border-rose-200]="!antiSpoofPassed()"
              [class.bg-rose-50]="!antiSpoofPassed()"
              [class.text-rose-700]="!antiSpoofPassed()"
              [class.border-primary-200]="antiSpoofPassed()"
              [class.bg-primary-50]="antiSpoofPassed()"
              [class.text-primary-700]="antiSpoofPassed()"
            >
              3. Validation Passed
            </div>
          </div>

          @if (antiSpoofStatus()) {
            <div class="mt-4 rounded-2xl border border-rose-100 bg-rose-50/60 p-4 text-sm text-slate-700">
              <p><span class="font-semibold">Status:</span> {{ antiSpoofStatus()?.status }}</p>
              <p><span class="font-semibold">Final Decision:</span> {{ antiSpoofStatus()?.finalDecision || 'pending' }}</p>
              <p><span class="font-semibold">Retry Count:</span> {{ antiSpoofStatus()?.retryCount }}</p>
              @if (antiSpoofStatus()?.latestSummary) {
                <p class="mt-2 text-xs text-slate-600">{{ antiSpoofStatus()?.latestSummary }}</p>
              }
            </div>
          }

          @if (antiSpoofChallenge()) {
            <div class="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4">
              <p class="text-xs font-semibold uppercase tracking-wide text-primary-700">
                Challenge: {{ antiSpoofChallenge()?.challengeType }}
              </p>
              <p class="mt-2 text-base font-semibold text-slate-900">{{ antiSpoofChallenge()?.prompt }}</p>
              <ul class="mt-2 space-y-1 text-sm text-slate-700">
                @for (instruction of antiSpoofChallenge()?.instructions ?? []; track instruction) {
                  <li>- {{ instruction }}</li>
                }
              </ul>
            </div>
          }

          <div class="mt-4 grid gap-4 lg:grid-cols-2">
            <div class="rounded-2xl border border-rose-100 bg-rose-50/60 p-4">
              <p class="mb-2 text-sm font-medium text-slate-800">Live Camera + Audio</p>
              <div class="relative overflow-hidden rounded-xl bg-slate-900 aspect-video">
                <video #antiSpoofPreview autoplay playsinline muted class="h-full w-full object-cover"></video>
                @if (!cameraReady()) {
                  <div class="absolute inset-0 flex items-center justify-center text-xs text-slate-300">
                    Camera inactive
                  </div>
                }
              </div>

              <div class="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  (click)="startCamera()"
                  [disabled]="antiSpoofLoading()"
                  class="rounded-xl border border-rose-200 bg-white px-3 py-2 text-xs font-semibold text-rose-700 transition-colors hover:bg-rose-50 disabled:opacity-50"
                >
                  Start Camera
                </button>

                <button
                  type="button"
                  (click)="recordAntiSpoofClip()"
                  [disabled]="!cameraReady() || antiSpoofLoading() || recordingVideo() || !antiSpoofChallenge()"
                  class="rounded-xl bg-primary-600 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-700 disabled:opacity-50"
                >
                  {{ !antiSpoofChallenge() ? 'Issue Challenge First' : (recordingVideo() ? 'Recording...' : 'Record 10s Challenge Clip') }}
                </button>

                <button
                  type="button"
                  (click)="retakeRecordedClip()"
                  [disabled]="!recordedVideoFile() || antiSpoofLoading()"
                  class="rounded-xl border border-rose-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-rose-50 disabled:opacity-50"
                >
                  Retake
                </button>
              </div>

              <p class="mt-3 text-xs text-slate-600">
                @if (!antiSpoofChallenge()) {
                  Start by requesting a challenge prompt.
                } @else if (!recordedVideoFile()) {
                  Follow the prompt, then record and submit a 10-second MP4 or WebM clip.
                } @else {
                  Clip captured. Validate now to proceed to questions.
                }
              </p>
            </div>

            <div class="rounded-2xl border border-rose-100 bg-white p-4">
              <p class="mb-2 text-sm font-medium text-slate-800">Recorded Clip</p>

              @if (recordedVideoUrl()) {
                <video [src]="recordedVideoUrl()" controls class="aspect-video w-full rounded-xl border border-rose-100 bg-slate-900"></video>
                <p class="mt-2 text-xs text-slate-500">
                  {{ recordedVideoFile()?.name }}
                </p>
              } @else {
                <div class="flex aspect-video items-center justify-center rounded-xl border border-dashed border-rose-200 bg-rose-50/60 text-xs text-slate-500">
                  No clip recorded yet.
                </div>
              }

              <div class="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  (click)="submitAntiSpoofClip()"
                  [disabled]="!recordedVideoFile() || antiSpoofLoading() || recordingVideo()"
                  class="rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-rose-700 disabled:opacity-50"
                >
                  {{ antiSpoofLoading() ? (launchingAssessment() ? 'Opening Assessment...' : 'Validating...') : 'Validate Anti-Spoof' }}
                </button>

                <button
                  type="button"
                  (click)="issueNewChallenge()"
                  [disabled]="antiSpoofLoading() || recordingVideo()"
                  class="rounded-xl border border-rose-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-rose-50 disabled:opacity-50"
                >
                  New Challenge
                </button>
              </div>
            </div>
          </div>

          @if (antiSpoofAnalysis()) {
            <div class="mt-4 rounded-2xl border border-rose-100 bg-rose-50/60 p-4 text-sm text-slate-700">
              <p>
                <span class="font-semibold">Analysis:</span>
                {{ antiSpoofAnalysis()?.overallStatus }}
                ({{ antiSpoofAnalysis()?.overallScore | number:'1.0-1' }})
              </p>
              <p class="mt-1">{{ antiSpoofAnalysis()?.summary }}</p>
              @if ((antiSpoofAnalysis()?.reasons?.length ?? 0) > 0) {
                <ul class="mt-2 space-y-1 text-xs text-slate-600">
                  @for (reason of antiSpoofAnalysis()?.reasons ?? []; track reason) {
                    <li>- {{ reason }}</li>
                  }
                </ul>
              }
            </div>
          }

          @if (cameraError()) {
            <div class="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {{ cameraError() }}
            </div>
          }

          @if (antiSpoofError()) {
            <div class="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {{ antiSpoofError() }}
            </div>
          }
        </section>
      } @else if (!examStarted()) {
        <section class="rounded-3xl border border-rose-100 bg-white p-6 shadow-sm shadow-rose-100/70">
          <div class="space-y-4">
            <div class="rounded-2xl border border-rose-100 bg-rose-50/60 p-4 text-sm">
              <p class="font-semibold text-slate-900">Booked Slot</p>
              @if (dataService.scheduledExam()) {
                <p class="mt-2 text-slate-600">
                  {{ dataService.scheduledExam()?.date }} at {{ dataService.scheduledExam()?.time }}
                  @if (dataService.scheduledExam()?.timezone) {
                    ({{ dataService.scheduledExam()?.timezone }})
                  }
                </p>
              } @else {
                <p class="mt-2 text-slate-600">No active booked slot found for this account.</p>
              }
            </div>

            <div class="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
              Anti-spoof verification is mandatory and starts before L0 questions are generated.
            </div>

            <button
              type="button"
              (click)="startAssessment()"
              [disabled]="startingAssessment() || !canStartAssessment()"
              class="rounded-xl bg-primary-600 px-6 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {{ startingAssessment() ? 'Preparing Session...' : 'Start Assessment' }}
            </button>

            @if (!canStartAssessment()) {
              <p class="text-xs text-slate-500">
                Use the assessment link sent to your email after slot booking.
              </p>
            }
          </div>
        </section>
      } @else {
        <section class="surface-card overflow-hidden">
          <header class="border-b border-[var(--brand-line)] bg-[rgba(121,47,140,0.04)] p-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div class="flex flex-wrap items-center gap-3">
                <span class="rounded-full bg-white px-3 py-1 text-xs font-semibold text-[var(--brand-ink)]">
                  {{ currentPromptBadge() }}
                </span>
                @if (currentProgressLabel()) {
                  <span class="rounded-full bg-[rgba(203,30,75,0.10)] px-3 py-1 text-xs font-semibold text-[var(--brand-red)]">
                    {{ currentProgressLabel() }}
                  </span>
                }
                <span class="rounded-full px-3 py-1 text-xs font-semibold" [class]="proctoringConnected() ? 'bg-[rgba(166,37,104,0.10)] text-[var(--brand-berry)]' : 'bg-[#fff1f3] text-[#b42318]'">
                  {{ proctoringStatus() }}
                </span>
              </div>
              <div class="flex flex-wrap items-center gap-2 text-xs text-[var(--brand-copy-soft)]">
                <span>Fullscreen: {{ fullscreenActive() ? 'On' : 'Off' }}</span>
                <span>Vision: {{ visionMonitoringAvailable() ? 'On' : 'Limited' }}</span>
              </div>
            </div>
          </header>

          <div class="grid gap-0 lg:grid-cols-[1.45fr_0.75fr]">
            <main class="min-w-0 border-b border-[var(--brand-line)] p-6 lg:border-b-0 lg:border-r">
              @if (currentQuestionItem()) {
                <p class="eyebrow">{{ currentPromptSectionLabel() }}</p>
                <h2 class="mt-3 text-2xl font-semibold text-[var(--brand-ink)]">{{ currentQuestionItem()?.prompt }}</h2>
                <p class="soft-note mt-3">{{ stageSupportText(currentQuestionItem()?.stage || 'ROLE_SPECIFIC') }}</p>

                @if (currentQuestionRequiresAnswer()) {
                  <textarea
                    [value]="answerDraft()"
                    (input)="onAnswerInput($event)"
                    [rows]="isCodingStage() ? 14 : 8"
                    class="mt-6 w-full resize-none rounded-[1.3rem] border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] px-4 py-4 text-[var(--brand-ink)] outline-none focus:border-primary-500 focus:bg-white focus:ring-2 focus:ring-primary-500/15"
                    [class.font-mono]="isCodingStage()"
                    [placeholder]="isCodingStage() ? 'Write code, explain your approach, and keep your solution clear...' : 'Type your answer clearly and stay on topic...'"
                  ></textarea>

                  <div class="mt-4 rounded-[1.3rem] border border-[var(--brand-line)] bg-white p-4">
                    <div class="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p class="text-sm font-semibold text-[var(--brand-ink)]">Spoken Answer Capture</p>
                        <p class="mt-1 text-xs text-[var(--brand-copy-soft)]">
                          Record your response and transcribe it with the local Whisper model before submitting.
                        </p>
                      </div>
                      @if (answerTranscriptModel()) {
                        <span class="rounded-full bg-[rgba(166,37,104,0.10)] px-3 py-1 text-[11px] font-semibold text-[var(--brand-berry)]">
                          {{ answerTranscriptModel() }}
                        </span>
                      }
                    </div>

                    <div class="mt-4 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        (click)="toggleAnswerRecording()"
                        [disabled]="transcribingAnswer() || submittingAnswer() || finishingExam()"
                        class="rounded-full border border-[var(--brand-line)] bg-white px-4 py-2 text-xs font-semibold text-[var(--brand-ink)] hover:bg-[rgba(121,47,140,0.04)] disabled:opacity-50"
                      >
                        {{ recordingAnswerAudio() ? 'Stop And Transcribe' : 'Record Spoken Answer' }}
                      </button>

                      <button
                        type="button"
                        (click)="clearAnswerTranscript()"
                        [disabled]="recordingAnswerAudio() || transcribingAnswer() || !answerTranscript()"
                        class="rounded-full border border-[var(--brand-line)] bg-white px-4 py-2 text-xs font-semibold text-[var(--brand-copy-soft)] hover:bg-[rgba(121,47,140,0.04)] disabled:opacity-50"
                      >
                        Clear Transcript
                      </button>

                      @if (recordingAnswerAudio()) {
                        <span class="rounded-full bg-[#fff1f3] px-3 py-1 text-[11px] font-semibold text-[#b42318]">
                          Recording {{ formatRecordingSeconds(answerRecordingSeconds()) }}
                        </span>
                      }

                      @if (transcribingAnswer()) {
                        <span class="rounded-full bg-[rgba(166,37,104,0.10)] px-3 py-1 text-[11px] font-semibold text-[var(--brand-berry)]">
                          Transcribing with Whisper...
                        </span>
                      }
                    </div>

                    @if (answerTranscript()) {
                      <div class="mt-4 rounded-2xl border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] p-4">
                        <p class="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--brand-copy-soft)]">Captured Transcript</p>
                        <p class="mt-2 whitespace-pre-wrap text-sm leading-6 text-[var(--brand-ink)]">{{ answerTranscript() }}</p>
                      </div>
                    }
                  </div>
                } @else {
                  <div class="mt-6 rounded-[1.5rem] border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] p-6 text-sm leading-7 text-[var(--brand-copy-soft)]">
                    {{ currentQuestionRequiresAction() ? 'Review the AI guidance and continue when you are ready.' : 'This prompt is for information only.' }}
                  </div>
                }
              } @else {
                <div class="flex h-full items-center justify-center text-sm text-[var(--brand-copy-soft)]">
                  Unable to load assessment questions for this session.
                </div>
              }
            </main>

            <aside class="space-y-4 p-6">
              <div class="rounded-[1.3rem] border border-[var(--brand-line)] bg-[rgba(121,47,140,0.03)] p-4">
                <p class="text-sm font-semibold text-[var(--brand-ink)]">Live proctor preview</p>
                <div class="relative mt-3 overflow-hidden rounded-[1rem] bg-[var(--brand-ink)] aspect-video">
                  <video #assessmentPreview autoplay playsinline muted class="h-full w-full object-cover"></video>
                  @if (!cameraReady()) {
                    <div class="absolute inset-0 flex items-center justify-center text-xs text-white/70">Camera inactive</div>
                  }
                </div>
              </div>

              <div class="rounded-[1.3rem] border border-[var(--brand-line)] bg-white p-4">
                <p class="text-sm font-semibold text-[var(--brand-ink)]">Assessment rules</p>
                <div class="mt-3 space-y-2 text-sm text-[var(--brand-copy-soft)]">
                  <p>Stay on this tab and remain in fullscreen.</p>
                  <p>Tab switching gets two warnings. The third switch ends the session.</p>
                  <p>Face missing gets two warnings. The third face-missing warning ends the session.</p>
                  <p>Multiple faces terminate immediately. Gaze warnings are recorded but do not auto-terminate.</p>
                  <p>Copy, paste, and context-menu shortcuts are disabled during the live assessment.</p>
                </div>
              </div>

              @if (warningEvents().length > 0) {
                <div class="rounded-[1.3rem] border border-[#fed7d7] bg-[#fff5f5] p-4">
                  <p class="text-sm font-semibold text-[#b42318]">Recent proctor warnings</p>
                  <div class="mt-3 space-y-2 text-xs text-[#b42318]">
                    @for (warning of warningEvents(); track warning) {
                      <p>{{ warning }}</p>
                    }
                  </div>
                </div>
              }
            </aside>
          </div>

          <footer class="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--brand-line)] bg-[rgba(121,47,140,0.04)] p-5">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-sm text-[var(--brand-copy-soft)]">{{ footerMessage() }}</span>
              @if (voicePlaybackSupported()) {
                <button
                  type="button"
                  (click)="speakCurrentQuestion()"
                  class="rounded-full border border-[var(--brand-line)] bg-white px-3 py-1.5 text-xs font-semibold text-[var(--brand-ink)] hover:bg-[rgba(121,47,140,0.04)]"
                >
                  Read Prompt
                </button>
              }
            </div>
            <button
              type="button"
              (click)="nextQuestionOrSubmit()"
              [disabled]="!canAdvanceCurrentPrompt()"
              class="auth-primary-button !w-auto px-6 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {{ actionButtonLabel() }}
            </button>
          </footer>
        </section>
      }

      @if (dataService.errorMessage()) {
        <div class="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {{ dataService.errorMessage() }}
        </div>
      }

      @if (activeWarningDialog()) {
        <div class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4">
          <div class="w-full max-w-md rounded-[1.8rem] border border-[#f3d1db] bg-white p-6 shadow-2xl shadow-[rgba(70,24,49,0.18)]">
            <div class="flex items-start gap-3">
              <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-[#fff1f3] text-[#b42318]">
                <mat-icon>warning</mat-icon>
              </div>
              <div class="min-w-0">
                <p class="text-lg font-semibold text-[var(--brand-ink)]">{{ activeWarningDialog()!.title }}</p>
                <p class="mt-2 text-sm leading-7 text-[var(--brand-copy-soft)]">{{ activeWarningDialog()!.message }}</p>
              </div>
            </div>

            <div class="mt-6 flex justify-end">
              <button
                type="button"
                (click)="dismissWarningDialog()"
                class="rounded-full bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-700"
              >
                Continue Assessment
              </button>
            </div>
          </div>
        </div>
      }
    </div>
  `,
})
export class AssessmentSessionComponent implements OnInit, OnDestroy {
  @ViewChild('antiSpoofPreview') antiSpoofPreview?: ElementRef<HTMLVideoElement>;
  @ViewChild('assessmentPreview') assessmentPreview?: ElementRef<HTMLVideoElement>;

  dataService = inject(DataService);

  assessmentPhase = signal<AssessmentPhase>('idle');

  examStarted = signal(false);
  startingAssessment = signal(false);
  submittingAnswer = signal(false);
  finishingExam = signal(false);
  assessmentResult = signal<AssessmentResult | null>(null);
  terminatedSession = signal(false);
  terminationReason = signal<string | null>(null);
  warningEvents = signal<string[]>([]);

  assessmentSessionId = signal<string | null>(null);
  assessmentJobId = signal<string | null>(null);
  assessmentWebsocketUrl = signal('');
  assessmentQuestions = signal<AssessmentQuestion[]>([]);
  answerDraft = signal('');
  currentQuestion = signal(1);
  voicePlaybackSupported = signal(typeof window !== 'undefined' && 'speechSynthesis' in window);
  answerTranscript = signal<string | null>(null);
  answerTranscriptModel = signal<string | null>(null);
  transcribingAnswer = signal(false);
  recordingAnswerAudio = signal(false);
  answerRecordingSeconds = signal(0);
  activeWarningDialog = signal<WarningDialog | null>(null);

  antiSpoofSessionId = signal('');
  antiSpoofStatus = signal<AntiSpoofStatus | null>(null);
  antiSpoofChallenge = signal<AntiSpoofChallenge | null>(null);
  antiSpoofAnalysis = signal<AntiSpoofAnalysis | null>(null);
  antiSpoofLoading = signal(false);
  launchingAssessment = signal(false);
  antiSpoofPassed = computed(() => {
    if (this.isAntiSpoofPassed(this.antiSpoofStatus())) {
      return true;
    }

    return (this.antiSpoofAnalysis()?.overallStatus ?? '').toUpperCase() === 'PASS';
  });

  cameraReady = signal(false);
  cameraError = signal<string | null>(null);
  antiSpoofError = signal<string | null>(null);
  recordingVideo = signal(false);
  recordedVideoFile = signal<File | null>(null);
  recordedVideoUrl = signal<string | null>(null);

  proctoringConnected = signal(false);
  proctoringStatus = signal('Not connected');
  visionMonitoringAvailable = signal(false);
  fullscreenActive = signal(false);

  private proctoringSocket: WebSocket | null = null;
  private mediaStream: MediaStream | null = null;
  private previewStream: MediaStream | null = null;
  private activeRecorder: MediaRecorder | null = null;
  private heartbeatTimer: number | null = null;
  private visionMonitorTimer: number | null = null;
  private readonly proctorCooldowns = new Map<string, number>();
  private readonly warningDialogQueue: WarningDialog[] = [];
  private readonly localGuardCooldowns = new Map<string, number>();
  private warningDialogSequence = 0;
  private lastTabSwitchAt = 0;
  private gazeAwayStartedAt: number | null = null;
  private visionCheckInFlight = false;
  private readonly visionCanvas = typeof document !== 'undefined' ? document.createElement('canvas') : null;
  private answerAudioContext: AudioContext | null = null;
  private answerAudioSource: MediaStreamAudioSourceNode | null = null;
  private answerAudioProcessor: ScriptProcessorNode | null = null;
  private answerAudioSink: MediaStreamAudioDestinationNode | null = null;
  private answerAudioInputStream: MediaStream | null = null;
  private answerAudioChunks: Float32Array[] = [];
  private answerAudioSampleRate = 16000;
  private answerRecordingTimer: number | null = null;
  private answerRecordingStopTimer: number | null = null;
  private readonly visibilityHandler = () => {
    if (document.visibilityState === 'hidden') {
      this.reportTabSwitch('Assessment tab became hidden.');
    }
  };
  private readonly blurHandler = () => {
    window.setTimeout(() => {
      if (!this.examStarted()) {
        return;
      }
      if (document.visibilityState === 'hidden' || !document.hasFocus()) {
        this.reportTabSwitch('Assessment window lost focus.');
      }
    }, 120);
  };
  private readonly pageHideHandler = () => {
    this.reportTabSwitch('Assessment tab became hidden.');
  };
  private readonly fullscreenHandler = () => {
    const active = Boolean(document.fullscreenElement);
    this.fullscreenActive.set(active);
    if (!active && this.examStarted()) {
      void this.reportProctorEvent('fullscreen_exit', 'CRITICAL', {message: 'Fullscreen mode exited.'});
    }
  };
  private readonly clipboardGuardHandler = (event: ClipboardEvent) => {
    if (!this.examStarted()) {
      return;
    }

    event.preventDefault();
    this.pushLocalGuardNotice('Copy, cut, and paste are disabled during the live assessment.', 'clipboard');
  };
  private readonly contextMenuGuardHandler = (event: MouseEvent) => {
    if (!this.examStarted()) {
      return;
    }

    event.preventDefault();
    this.pushLocalGuardNotice('Right-click is disabled during the live assessment.', 'contextmenu');
  };
  private readonly keydownGuardHandler = (event: KeyboardEvent) => {
    if (!this.examStarted()) {
      return;
    }

    const key = event.key.toLowerCase();
    const usesModifier = event.ctrlKey || event.metaKey;
    const blockedShortcut = usesModifier && ['a', 'c', 'p', 's', 'u', 'v', 'x'].includes(key);
    if (blockedShortcut || key === 'f12') {
      event.preventDefault();
      this.pushLocalGuardNotice('Protected assessment mode is active. Browser shortcuts are limited.', 'shortcut');
    }
  };

  readonly canStartAssessment = computed(() => Boolean(this.dataService.scheduledExam()?.scheduleId));

  ngOnInit(): void {
    void this.initialize();
  }

  private async initialize(): Promise<void> {
    this.resetAssessmentState();
    await this.dataService.loadCandidateSchedules();
  }

  ngOnDestroy(): void {
    this.cleanupAssessmentGuards();
    this.disconnectProctoringSocket();
    this.abortAnswerRecording();
    this.stopPromptPlayback();
    this.stopCamera();
  }

  async startAssessment(): Promise<void> {
    if (this.examStarted() || this.startingAssessment()) {
      return;
    }

    await this.enterFullscreen();

    if (!this.canStartAssessment()) {
      await this.dataService.loadCandidateSchedules();
      if (!this.canStartAssessment()) {
        this.dataService.errorMessage.set('No booked slot found. Book a slot first using your invitation link.');
        return;
      }
    }

    try {
      this.startingAssessment.set(true);
      this.resetAssessmentState();
      this.assessmentResult.set(null);
      this.terminatedSession.set(false);
      this.terminationReason.set(null);
      this.warningEvents.set([]);
      const session = await this.dataService.startAssessmentSession();

      this.assessmentSessionId.set(session.sessionId);
      this.assessmentJobId.set(session.jobId);
      this.assessmentWebsocketUrl.set(session.websocketUrl);
      this.antiSpoofSessionId.set(session.antiSpoofSessionId);
      this.currentQuestion.set(1);
      this.answerDraft.set('');
      this.terminationReason.set(session.terminationReason);

      if (session.antiSpoofSessionId) {
        this.assessmentPhase.set('anti_spoof');
        await this.initializeAntiSpoofGate();
        return;
      }

      await this.beginAssessmentQuestions();
    } catch {
      this.resetAssessmentState();
    } finally {
      this.startingAssessment.set(false);
    }
  }

  currentQuestionItem(): AssessmentQuestion | null {
    const index = this.currentQuestion() - 1;
    return this.assessmentQuestions()[index] ?? null;
  }

  showAssessmentScore(): boolean {
    const result = this.assessmentResult();
    return Boolean(result && !this.terminatedSession() && Number.isFinite(result.overallScore));
  }

  isLastQuestion(): boolean {
    return this.currentQuestion() >= this.assessmentQuestions().length;
  }

  onAnswerInput(event: Event): void {
    const input = event.target as HTMLTextAreaElement;
    this.answerDraft.set(input.value);
  }

  currentQuestionRequiresAnswer(): boolean {
    const question = this.currentQuestionItem();
    return Boolean(question && !this.isSystemStage(question.stage));
  }

  currentQuestionRequiresAction(): boolean {
    const question = this.currentQuestionItem();
    return Boolean(question && this.isSystemStage(question.stage));
  }

  currentPromptBadge(): string {
    const question = this.currentQuestionItem();
    if (!question) {
      return 'Assessment Prompt';
    }

    const labels: Record<string, string> = {
      INTRO: 'AI Introduction',
      CANDIDATE_INFO: 'Candidate Introduction',
      ROLE_SPECIFIC: 'JD Interview',
      CODING: 'Coding Round',
      SUMMARY: 'AI Closing Summary',
    };
    return labels[(question.stage ?? '').toUpperCase()] ?? 'Assessment Prompt';
  }

  currentPromptSectionLabel(): string {
    const question = this.currentQuestionItem();
    if (!question) {
      return 'Assessment';
    }

    const stage = (question.stage ?? '').toUpperCase();
    if (stage === 'INTRO' || stage === 'SUMMARY') {
      return 'AI Interviewer';
    }
    if (stage === 'CANDIDATE_INFO') {
      return 'About You';
    }
    if (stage === 'CODING') {
      return 'Coding Challenge';
    }
    return 'Role-Fit Question';
  }

  currentProgressLabel(): string | null {
    const question = this.currentQuestionItem();
    if (!question) {
      return null;
    }

    const stage = (question.stage ?? '').toUpperCase();
    if (stage === 'INTRO') {
      return `Step 1 of ${this.assessmentQuestions().length}`;
    }
    if (stage === 'SUMMARY') {
      return 'Final step';
    }
    if (stage === 'CANDIDATE_INFO') {
      return 'Candidate introduction';
    }
    return `JD question ${this.displayQuestionIndex()} of ${this.answerableQuestionCount()}`;
  }

  footerMessage(): string {
    const question = this.currentQuestionItem();
    if (!question) {
      return 'Loading the live assessment prompt.';
    }

    const stage = (question.stage ?? '').toUpperCase();
    if (stage === 'INTRO') {
      return 'The AI will introduce the assessment flow first. No response is needed yet.';
    }
    if (stage === 'SUMMARY') {
      return 'Review the closing message and submit the assessment when you are ready.';
    }
    if (stage === 'CANDIDATE_INFO') {
      return 'Start with a concise self-introduction before the JD-focused questions begin.';
    }
    if (stage === 'CODING') {
      return 'Keep your solution readable, explain tradeoffs, and stay aligned with the role requirements.';
    }
    return 'Answer based on the job description and keep your responses focused and clear.';
  }

  actionButtonLabel(): string {
    const question = this.currentQuestionItem();
    if (!question) {
      return 'Continue';
    }

    const stage = (question.stage ?? '').toUpperCase();
    if (stage === 'INTRO') {
      return 'Begin Assessment';
    }
    if (stage === 'SUMMARY') {
      return this.finishingExam() ? 'Submitting...' : 'Finish Assessment';
    }
    if (this.isFinalAnswerablePrompt()) {
      return this.submittingAnswer() ? 'Submitting...' : 'Submit And Continue';
    }
    return this.submittingAnswer() ? 'Submitting...' : 'Submit Answer';
  }

  canAdvanceCurrentPrompt(): boolean {
    const question = this.currentQuestionItem();
    if (!question || this.submittingAnswer() || this.finishingExam()) {
      return false;
    }

    if (this.currentQuestionRequiresAction()) {
      return true;
    }

    if (this.recordingAnswerAudio() || this.transcribingAnswer()) {
      return false;
    }

    return this.answerDraft().trim().length > 0;
  }

  async nextQuestionOrSubmit(): Promise<void> {
    const question = this.currentQuestionItem();
    const sessionId = this.assessmentSessionId();
    const answer = this.answerDraft().trim();

    if (!question || !sessionId) {
      return;
    }

    if (!this.currentQuestionRequiresAnswer()) {
      if (this.isLastQuestion()) {
        await this.finishExam();
        return;
      }

      this.advanceToNextPrompt();
      return;
    }

    if (!answer) {
      return;
    }

    try {
      this.submittingAnswer.set(true);
      await this.dataService.submitAssessmentAnswer(
        sessionId,
        question.id,
        answer,
        this.answerTranscript(),
        this.answerTranscriptModel(),
      );

      if (this.isLastQuestion()) {
        await this.finishExam();
        return;
      }

      this.advanceToNextPrompt();
    } finally {
      this.submittingAnswer.set(false);
    }
  }

  async issueNewChallenge(): Promise<void> {
    const sessionId = this.assessmentSessionId();
    if (!sessionId) {
      return;
    }

    try {
      this.antiSpoofLoading.set(true);
      this.antiSpoofError.set(null);
      this.antiSpoofChallenge.set(await this.dataService.issueAntiSpoofChallenge(sessionId));
      this.antiSpoofAnalysis.set(null);
    } finally {
      this.antiSpoofLoading.set(false);
    }
  }

  async startCamera(): Promise<void> {
    this.cameraError.set(null);
    this.antiSpoofError.set(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      this.cameraError.set('Camera and microphone access are not supported in this browser.');
      return;
    }

    try {
      this.stopCamera();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: {ideal: 1280},
          height: {ideal: 720},
        },
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000,
        },
      });

      this.mediaStream = stream;
      this.refreshPreviewStream();
      this.cameraReady.set(true);
      this.attachStreamToActivePreview();
      if (this.examStarted()) {
        this.beginVisionMonitoring();
      }

      for (const track of stream.getVideoTracks()) {
        track.onended = () => {
          void this.reportProctorEvent('camera_lost', 'CRITICAL', {
            message: 'Camera stream ended unexpectedly.',
          });
          this.cameraReady.set(false);
        };
      }
    } catch {
      this.cameraError.set('Camera or microphone permission was denied. Please allow access and retry.');
      this.stopCamera();
    }
  }

  async recordAntiSpoofClip(): Promise<void> {
    if (!this.mediaStream || !this.cameraReady()) {
      this.cameraError.set('Start camera and microphone before recording.');
      return;
    }

    if (typeof MediaRecorder === 'undefined') {
      this.cameraError.set('Video recording is not supported in this browser.');
      return;
    }

    const mimeType = this.resolveRecorderMimeType();

    try {
      this.recordingVideo.set(true);
      this.cameraError.set(null);

      const recorder = mimeType
        ? new MediaRecorder(this.mediaStream, {mimeType})
        : new MediaRecorder(this.mediaStream);
      this.activeRecorder = recorder;

      const chunks: BlobPart[] = [];
      const recordingFinished = new Promise<Blob>((resolve, reject) => {
        recorder.ondataavailable = (event: BlobEvent) => {
          if (event.data.size > 0) {
            chunks.push(event.data);
          }
        };
        recorder.onerror = () => reject(new Error('Recording failed.'));
        recorder.onstop = () => {
          resolve(new Blob(chunks, {type: recorder.mimeType || mimeType || 'video/webm'}));
        };
      });

      recorder.start(250);
      window.setTimeout(() => {
        if (recorder.state !== 'inactive') {
          recorder.stop();
        }
      }, 10000);

      const blob = await recordingFinished;
      const extension = blob.type.includes('mp4') ? 'mp4' : 'webm';
      const file = new File([blob], `anti-spoof-${Date.now()}.${extension}`, {type: blob.type || 'video/webm'});

      const existingUrl = this.recordedVideoUrl();
      if (existingUrl) {
        URL.revokeObjectURL(existingUrl);
      }

      this.recordedVideoFile.set(file);
      this.recordedVideoUrl.set(URL.createObjectURL(file));
      this.antiSpoofAnalysis.set(null);
      this.antiSpoofError.set(null);
      this.stopCamera();
    } catch {
      this.cameraError.set('Unable to record challenge clip. Please retry.');
    } finally {
      this.recordingVideo.set(false);
      this.activeRecorder = null;
    }
  }

  retakeRecordedClip(): void {
    const existingUrl = this.recordedVideoUrl();
    if (existingUrl) {
      URL.revokeObjectURL(existingUrl);
    }

    this.recordedVideoFile.set(null);
    this.recordedVideoUrl.set(null);
    this.antiSpoofAnalysis.set(null);
    this.antiSpoofError.set(null);
    void this.startCamera();
  }

  async submitAntiSpoofClip(): Promise<void> {
    const file = this.recordedVideoFile();
    const sessionId = this.assessmentSessionId();
    if (!file || !sessionId) {
      return;
    }

    try {
      this.antiSpoofLoading.set(true);
      this.antiSpoofError.set(null);
      const analysis = await this.dataService.analyzeAntiSpoof(sessionId, file);
      this.antiSpoofAnalysis.set(analysis);

      const status = await this.dataService.getAntiSpoofStatus(sessionId);
      this.antiSpoofStatus.set(status);

      if (this.isAntiSpoofPassed(status) || analysis.overallStatus.toUpperCase() === 'PASS') {
        await this.finalizeAntiSpoofAndBeginAssessment();
        return;
      }

      if (analysis.retryAllowed) {
        this.antiSpoofError.set(analysis.summary || analysis.reasons.join(', ') || 'Anti-spoof validation did not pass. Please try the next challenge.');
        await this.issueNewChallenge();
        return;
      }

      this.antiSpoofError.set(
        analysis.summary
        || analysis.reasons.join(', ')
        || status.latestSummary
        || 'Anti-spoof validation did not pass for this session.',
      );
    } catch {
      if (await this.tryResumeAfterAntiSpoofDelay(sessionId)) {
        return;
      }

      this.antiSpoofError.set(this.dataService.errorMessage() ?? 'Unable to validate anti-spoof submission right now.');
    } finally {
      this.antiSpoofLoading.set(false);
    }
  }

  private async finishExam(): Promise<void> {
    const sessionId = this.assessmentSessionId();
    if (!sessionId) {
      return;
    }

    try {
      this.finishingExam.set(true);
      this.abortAnswerRecording();
      const result = await this.dataService.finishAssessmentSession(sessionId);
      this.assessmentResult.set(result);
      this.terminationReason.set(result.terminationReason);
      this.cleanupAssessmentGuards();
      this.disconnectProctoringSocket();
      this.examStarted.set(false);
      this.assessmentPhase.set('idle');
    } finally {
      this.finishingExam.set(false);
    }
  }

  private async initializeAntiSpoofGate(): Promise<void> {
    const sessionId = this.assessmentSessionId();
    if (!sessionId) {
      return;
    }

    try {
      this.antiSpoofLoading.set(true);
      const status = await this.dataService.getAntiSpoofStatus(sessionId);
      this.antiSpoofStatus.set(status);

      if (this.isAntiSpoofPassed(status)) {
        await this.finalizeAntiSpoofAndBeginAssessment();
        return;
      }

      this.antiSpoofChallenge.set(await this.dataService.issueAntiSpoofChallenge(sessionId));
      window.setTimeout(() => {
        void this.startCamera();
      }, 0);
    } catch {
      this.antiSpoofError.set(this.dataService.errorMessage() ?? 'Unable to initialize anti-spoof verification.');
    } finally {
      this.antiSpoofLoading.set(false);
    }
  }

  private async finalizeAntiSpoofAndBeginAssessment(): Promise<void> {
    const sessionId = this.assessmentSessionId();
    if (!sessionId) {
      return;
    }

    try {
      this.launchingAssessment.set(true);
      const status = await this.dataService.finalizeAntiSpoof(sessionId);
      this.antiSpoofStatus.set(status);

      if (!this.isAntiSpoofPassed(status)) {
        return;
      }

      await this.beginAssessmentQuestions();
      return;
    } catch {
      if (await this.tryResumeAfterAntiSpoofDelay(sessionId, 3, 1500)) {
        return;
      }
      this.launchingAssessment.set(false);
      throw new Error(this.dataService.errorMessage() ?? 'Unable to finalize anti-spoof verification.');
    }
  }

  private async beginAssessmentQuestions(): Promise<void> {
    const sessionId = this.assessmentSessionId();
    const jobId = this.assessmentJobId();
    const websocketUrl = this.assessmentWebsocketUrl();

    if (!sessionId || !jobId) {
      throw new Error('Assessment session could not be initialized.');
    }

    const questions = await this.dataService.loadAssessmentQuestions(sessionId, jobId);
    if (questions.length === 0) {
      this.launchingAssessment.set(false);
      throw new Error('Assessment questions could not be loaded.');
    }

    this.assessmentQuestions.set(questions);
    this.currentQuestion.set(1);
    this.resetAnswerComposer();
    this.examStarted.set(true);
    this.assessmentPhase.set('questions');
    this.launchingAssessment.set(false);
    this.attachStreamToActivePreview();
    this.connectProctoringSocket(websocketUrl);
    this.setupAssessmentGuards();
    this.speakCurrentQuestion();
  }

  private connectProctoringSocket(websocketUrl: string): void {
    this.disconnectProctoringSocket();

    if (!websocketUrl) {
      this.proctoringConnected.set(false);
      this.proctoringStatus.set('Realtime channel unavailable');
      return;
    }

    this.proctoringStatus.set('Connecting proctoring channel...');
    try {
      this.proctoringSocket = new WebSocket(websocketUrl);
    } catch {
      this.proctoringConnected.set(false);
      this.proctoringStatus.set('Unable to initialize realtime channel');
      return;
    }

    this.proctoringSocket.onopen = () => {
      this.proctoringConnected.set(true);
      this.proctoringStatus.set('Realtime proctoring connected');
    };

    this.proctoringSocket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          event?: string;
          session_status?: string | null;
          termination_reason?: string | null;
        };

        if (payload.session_status === 'TERMINATED') {
          void this.handleTermination(payload.termination_reason ?? 'Session terminated by proctoring policy.');
        }
      } catch {
        // Ignore malformed realtime payloads.
      }
    };

    this.proctoringSocket.onclose = () => {
      this.proctoringConnected.set(false);
      this.proctoringStatus.set('Realtime proctoring disconnected');
    };

    this.proctoringSocket.onerror = () => {
      this.proctoringConnected.set(false);
      this.proctoringStatus.set('Realtime proctoring connection failed');
    };
  }

  private disconnectProctoringSocket(): void {
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.proctoringSocket) {
      this.proctoringSocket.close();
      this.proctoringSocket = null;
    }
    this.proctoringConnected.set(false);
    this.proctoringStatus.set('Not connected');
  }

  private resolveRecorderMimeType(): string | null {
    const options = [
      'video/mp4;codecs=h264,aac',
      'video/mp4',
      'video/webm;codecs=vp9,opus',
      'video/webm;codecs=vp8,opus',
      'video/webm',
    ];

    for (const option of options) {
      if (MediaRecorder.isTypeSupported(option)) {
        return option;
      }
    }

    return null;
  }

  private attachStreamToActivePreview(): void {
    if (!this.mediaStream) {
      return;
    }

    const preview = this.assessmentPhase() === 'questions'
      ? this.assessmentPreview?.nativeElement
      : this.antiSpoofPreview?.nativeElement;
    if (!preview) {
      window.setTimeout(() => this.attachStreamToActivePreview(), 0);
      return;
    }

    preview.srcObject = this.previewStream ?? this.mediaStream;
    preview.muted = true;
    preview.defaultMuted = true;
    preview.volume = 0;
    void preview.play().catch(() => {
      this.cameraError.set('Unable to start the live camera preview.');
    });
  }

  private setupAssessmentGuards(): void {
    if (!this.mediaStream) {
      void this.startCamera();
    } else {
      this.attachStreamToActivePreview();
    }

    document.addEventListener('visibilitychange', this.visibilityHandler);
    window.addEventListener('blur', this.blurHandler);
    window.addEventListener('pagehide', this.pageHideHandler);
    document.addEventListener('fullscreenchange', this.fullscreenHandler);
    document.addEventListener('copy', this.clipboardGuardHandler);
    document.addEventListener('cut', this.clipboardGuardHandler);
    document.addEventListener('paste', this.clipboardGuardHandler);
    document.addEventListener('contextmenu', this.contextMenuGuardHandler);
    document.addEventListener('keydown', this.keydownGuardHandler);

    this.fullscreenActive.set(Boolean(document.fullscreenElement));
    void this.enterFullscreen();

    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
    }
    this.heartbeatTimer = window.setInterval(() => {
      const sessionId = this.assessmentSessionId();
      if (sessionId) {
        void this.dataService.sendAssessmentHeartbeat(sessionId).catch(() => undefined);
      }
    }, 15000);

    this.beginVisionMonitoring();
  }

  private cleanupAssessmentGuards(): void {
    document.removeEventListener('visibilitychange', this.visibilityHandler);
    window.removeEventListener('blur', this.blurHandler);
    window.removeEventListener('pagehide', this.pageHideHandler);
    document.removeEventListener('fullscreenchange', this.fullscreenHandler);
    document.removeEventListener('copy', this.clipboardGuardHandler);
    document.removeEventListener('cut', this.clipboardGuardHandler);
    document.removeEventListener('paste', this.clipboardGuardHandler);
    document.removeEventListener('contextmenu', this.contextMenuGuardHandler);
    document.removeEventListener('keydown', this.keydownGuardHandler);

    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.visionMonitorTimer !== null) {
      window.clearInterval(this.visionMonitorTimer);
      this.visionMonitorTimer = null;
    }
    this.fullscreenActive.set(Boolean(document.fullscreenElement));
  }

  private async enterFullscreen(): Promise<void> {
    if (!document.documentElement.requestFullscreen || document.fullscreenElement) {
      this.fullscreenActive.set(Boolean(document.fullscreenElement));
      return;
    }

    try {
      await document.documentElement.requestFullscreen();
      this.fullscreenActive.set(true);
    } catch {
      this.fullscreenActive.set(Boolean(document.fullscreenElement));
    }
  }

  private beginVisionMonitoring(): void {
    this.visionMonitoringAvailable.set(Boolean(this.mediaStream));
    if (this.visionMonitorTimer !== null) {
      window.clearInterval(this.visionMonitorTimer);
      this.visionMonitorTimer = null;
    }

    if (!this.mediaStream) {
      return;
    }

    this.visionMonitorTimer = window.setInterval(() => {
      void this.monitorVisionFrame();
    }, 2000);
  }

  private async monitorVisionFrame(): Promise<void> {
    if (this.visionCheckInFlight) {
      return;
    }

    const preview = this.assessmentPreview?.nativeElement;
    if (!preview || preview.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      return;
    }

    try {
      this.visionCheckInFlight = true;
      const snapshot = await this.captureVisionSnapshot(preview);
      const sessionId = this.assessmentSessionId();
      if (!snapshot || !sessionId) {
        return;
      }

      const result = await this.dataService.analyzeAssessmentVision(sessionId, snapshot);
      this.visionMonitoringAvailable.set(true);

      if (result.faceCount === 0 || result.gazeStatus === 'NO_FACE') {
        this.gazeAwayStartedAt = null;
        await this.reportProctorEvent('face_missing', 'WARNING', {
          message: result.message ?? 'No face detected in camera frame.',
        });
        return;
      }

      if (result.faceCount > 1 || result.gazeStatus === 'MULTIPLE_FACES') {
        this.gazeAwayStartedAt = null;
        await this.reportProctorEvent('multiple_faces', 'CRITICAL', {
          message: result.message ?? 'Multiple faces detected in the camera frame.',
          face_count: result.faceCount,
        });
        return;
      }

      if (result.gazeStatus === 'AWAY') {
        const now = Date.now();
        if (this.gazeAwayStartedAt === null) {
          this.gazeAwayStartedAt = now;
          return;
        }

        const awayDurationMs = now - this.gazeAwayStartedAt;
        if (awayDurationMs < 4000) {
          return;
        }

        this.gazeAwayStartedAt = now;
        await this.reportProctorEvent('gaze_away', 'WARNING', {
          message: result.message ?? 'Candidate gaze stayed away from screen center for too long.',
          normalized_offset: result.normalizedOffset,
          away_duration_ms: awayDurationMs,
        });
        return;
      }

      this.gazeAwayStartedAt = null;
    } catch {
      this.visionMonitoringAvailable.set(false);
    } finally {
      this.visionCheckInFlight = false;
    }
  }

  private async reportProctorEvent(eventType: string, severity: ProctorSeverity, payload: Record<string, unknown>): Promise<void> {
    const sessionId = this.assessmentSessionId();
    if (!sessionId || !this.examStarted()) {
      return;
    }

    const cooldownKey = `${severity}:${eventType}`;
    const now = Date.now();
    const lastFiredAt = this.proctorCooldowns.get(cooldownKey) ?? 0;
    const cooldownMs = this.cooldownMsForEvent(eventType, severity);
    if (now - lastFiredAt < cooldownMs) {
      return;
    }

    this.proctorCooldowns.set(cooldownKey, now);
    try {
      const response = await this.dataService.ingestProctorEvent(sessionId, {
        eventType,
        severity,
        payload,
        eventTimestamp: new Date().toISOString(),
      });

      const warningMessage = response.warningMessage ?? (severity !== 'INFO' ? this.humanizeProctorEvent(eventType) : null);
      if (warningMessage) {
        this.pushWarningEvent(warningMessage);
      }
      if (response.shouldAcknowledge && warningMessage) {
        this.enqueueWarningDialog('Proctoring Warning', warningMessage);
      }

      if (response.sessionStatus === 'TERMINATED') {
        await this.handleTermination(response.terminationReason ?? 'Session terminated by proctoring policy.');
      }
    } catch {
      if (severity !== 'INFO') {
        this.pushWarningEvent(this.humanizeProctorEvent(eventType));
      }
    }
  }

  private cooldownMsForEvent(eventType: string, severity: ProctorSeverity): number {
    if (severity === 'CRITICAL') {
      return 0;
    }

    const map: Record<string, number> = {
      tab_switch: 1200,
      gaze_away: 10000,
      face_missing: 8000,
    };
    return map[eventType] ?? 5000;
  }

  private pushWarningEvent(message: string): void {
    this.warningEvents.update((events) => [message, ...events].slice(0, 4));
  }

  private pushLocalGuardNotice(message: string, key: string, cooldownMs = 4000): void {
    const now = Date.now();
    const lastShownAt = this.localGuardCooldowns.get(key) ?? 0;
    if (now - lastShownAt < cooldownMs) {
      return;
    }

    this.localGuardCooldowns.set(key, now);
    this.pushWarningEvent(message);
  }

  private enqueueWarningDialog(title: string, message: string): void {
    const dialog: WarningDialog = {
      id: ++this.warningDialogSequence,
      title,
      message,
    };

    if (!this.activeWarningDialog()) {
      this.activeWarningDialog.set(dialog);
      return;
    }

    this.warningDialogQueue.push(dialog);
  }

  dismissWarningDialog(): void {
    const next = this.warningDialogQueue.shift() ?? null;
    this.activeWarningDialog.set(next);
  }

  private reportTabSwitch(message: string): void {
    const now = Date.now();
    if (now - this.lastTabSwitchAt < 1200) {
      return;
    }

    this.lastTabSwitchAt = now;
    void this.reportProctorEvent('tab_switch', 'WARNING', {message});
  }

  private async captureVisionSnapshot(preview: HTMLVideoElement): Promise<File | null> {
    const canvas = this.visionCanvas;
    if (!canvas) {
      return null;
    }

    canvas.width = preview.videoWidth || 1280;
    canvas.height = preview.videoHeight || 720;
    const context = canvas.getContext('2d');
    if (!context) {
      return null;
    }

    context.drawImage(preview, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob((result) => resolve(result), 'image/jpeg', 0.82);
    });
    if (!blob) {
      return null;
    }

    return new File([blob], `vision-${Date.now()}.jpg`, {type: 'image/jpeg'});
  }

  private humanizeProctorEvent(eventType: string): string {
    const labels: Record<string, string> = {
      tab_switch: 'Tab switching was detected.',
      fullscreen_exit: 'Fullscreen mode was exited.',
      camera_lost: 'Camera feed was lost.',
      face_missing: 'Face visibility was lost.',
      multiple_faces: 'Multiple faces were detected. The assessment will be terminated.',
      gaze_away: 'Please keep your gaze on screen for at least a few seconds before looking away.',
    };
    return labels[eventType] ?? 'A proctoring event was detected.';
  }

  private isSystemStage(stage: string | null | undefined): boolean {
    const normalized = (stage ?? '').toUpperCase();
    return normalized === 'INTRO' || normalized === 'SUMMARY';
  }

  private answerableQuestionCount(): number {
    return this.assessmentQuestions().filter((question) => {
      const stage = (question.stage ?? '').toUpperCase();
      return stage === 'ROLE_SPECIFIC' || stage === 'CODING';
    }).length;
  }

  private displayQuestionIndex(): number {
    const current = this.currentQuestionItem();
    if (!current) {
      return 0;
    }

    const answerableStages = new Set(['ROLE_SPECIFIC', 'CODING']);
    let index = 0;
    for (const question of this.assessmentQuestions()) {
      const stage = (question.stage ?? '').toUpperCase();
      if (answerableStages.has(stage)) {
        index += 1;
      }
      if (question.id === current.id) {
        return index;
      }
    }

    return 0;
  }

  private isFinalAnswerablePrompt(): boolean {
    const current = this.currentQuestionItem();
    if (!current || !this.currentQuestionRequiresAnswer()) {
      return false;
    }

    const currentIndex = this.assessmentQuestions().findIndex((question) => question.id === current.id);
    if (currentIndex < 0) {
      return false;
    }

    return !this.assessmentQuestions()
      .slice(currentIndex + 1)
      .some((question) => !this.isSystemStage(question.stage));
  }

  private advanceToNextPrompt(): void {
    this.currentQuestion.set(this.currentQuestion() + 1);
    this.resetAnswerComposer();
    this.speakCurrentQuestion();
  }

  private async handleTermination(reason: string): Promise<void> {
    this.terminatedSession.set(true);
    this.terminationReason.set(reason);
    this.proctoringStatus.set('Session terminated');
    this.cleanupAssessmentGuards();
    this.disconnectProctoringSocket();
    this.warningDialogQueue.splice(0, this.warningDialogQueue.length);
    this.activeWarningDialog.set(null);
    this.abortAnswerRecording();
    this.stopPromptPlayback();
    this.examStarted.set(false);
    this.assessmentPhase.set('idle');
    this.gazeAwayStartedAt = null;

    const sessionId = this.assessmentSessionId();
    if (!sessionId) {
      return;
    }

    try {
      this.assessmentResult.set(await this.dataService.getAssessmentReport(sessionId));
    } catch {
      this.assessmentResult.set({
        overallScore: 0,
        decision: 'FAIL',
        summary: reason,
        sectionScores: {},
        reasons: [reason],
        proctorSummary: reason,
        terminationReason: reason,
        flaggedEventsTimeline: [],
        questionResults: [],
        generatedByModel: null,
      });
    }
  }

  humanizeStage(stage: string): string {
    const labels: Record<string, string> = {
      INTRO: 'AI Introduction',
      CANDIDATE_INFO: 'Candidate Introduction',
      ROLE_SPECIFIC: 'Role Question',
      CODING: 'Coding Question',
      SUMMARY: 'Closing Summary',
    };
    return labels[stage.toUpperCase()] ?? stage
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  isCodingStage(): boolean {
    return (this.currentQuestionItem()?.stage ?? '').toUpperCase() === 'CODING';
  }

  stageSupportText(stage: string): string {
    const normalized = stage.toUpperCase();
    if (normalized === 'INTRO') {
      return 'The AI interviewer will introduce the session, explain what will be covered from the job description, and then begin the assessment.';
    }
    if (normalized === 'CANDIDATE_INFO') {
      return 'Give a clear personal introduction so the manager understands your background before the role-focused questions start.';
    }
    if (normalized === 'CODING') {
      return 'Work through the problem in a structured way, keep the code readable, and explain key decisions as you go.';
    }
    if (normalized === 'SUMMARY') {
      return 'The AI interviewer closes the session with a positive summary and goodbye. No final answer is required here.';
    }
    return 'These questions are generated from the job description. Start with fundamentals, stay specific, and keep your face visible while responding.';
  }

  speakCurrentQuestion(): void {
    if (!this.voicePlaybackSupported() || typeof window === 'undefined' || !('speechSynthesis' in window)) {
      return;
    }

    const question = this.currentQuestionItem();
    if (!question) {
      return;
    }

    this.stopPromptPlayback();

    const utterance = new SpeechSynthesisUtterance(
      `${this.currentPromptBadge()}. ${question.prompt}. ${this.stageSupportText(question.stage)}`,
    );
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.lang = 'en-US';
    window.speechSynthesis.speak(utterance);
  }

  formatRecordingSeconds(value: number): string {
    const minutes = Math.floor(value / 60).toString().padStart(2, '0');
    const seconds = Math.floor(value % 60).toString().padStart(2, '0');
    return `${minutes}:${seconds}`;
  }

  async toggleAnswerRecording(): Promise<void> {
    if (this.recordingAnswerAudio()) {
      await this.finishAnswerRecording();
      return;
    }

    await this.startAnswerRecording();
  }

  clearAnswerTranscript(): void {
    this.answerTranscript.set(null);
    this.answerTranscriptModel.set(null);
  }

  private async startAnswerRecording(): Promise<void> {
    if (typeof window === 'undefined') {
      return;
    }

    if (this.transcribingAnswer()) {
      return;
    }

    if (!this.mediaStream) {
      await this.startCamera();
    }

    const sourceStream = this.mediaStream;
    const audioTracks = sourceStream?.getAudioTracks() ?? [];
    if (audioTracks.length === 0) {
      this.dataService.errorMessage.set('Microphone is not available. Allow microphone access to record your spoken answer.');
      return;
    }

    const AudioContextCtor = globalThis.AudioContext
      || (window as Window & {webkitAudioContext?: typeof AudioContext}).webkitAudioContext;
    if (!AudioContextCtor) {
      this.dataService.errorMessage.set('Audio recording is not supported in this browser.');
      return;
    }

    this.stopPromptPlayback();
    this.abortAnswerRecording();
    this.dataService.errorMessage.set(null);
    this.answerTranscript.set(null);
    this.answerTranscriptModel.set(null);
    this.answerAudioChunks = [];

    try {
      const inputStream = new MediaStream(audioTracks.map((track) => track.clone()));
      const audioContext = new AudioContextCtor({sampleRate: 16000});
      await audioContext.resume();

      const source = audioContext.createMediaStreamSource(inputStream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const sink = audioContext.createMediaStreamDestination();

      processor.onaudioprocess = (event: AudioProcessingEvent) => {
        const input = event.inputBuffer.getChannelData(0);
        this.answerAudioChunks.push(new Float32Array(input));

        const output = event.outputBuffer.getChannelData(0);
        output.fill(0);
      };

      source.connect(processor);
      processor.connect(sink);

      this.answerAudioContext = audioContext;
      this.answerAudioSource = source;
      this.answerAudioProcessor = processor;
      this.answerAudioSink = sink;
      this.answerAudioInputStream = inputStream;
      this.answerAudioSampleRate = audioContext.sampleRate || 16000;
      this.recordingAnswerAudio.set(true);
      this.answerRecordingSeconds.set(0);

      this.answerRecordingTimer = window.setInterval(() => {
        this.answerRecordingSeconds.update((value) => value + 1);
      }, 1000);

      this.answerRecordingStopTimer = window.setTimeout(() => {
        void this.finishAnswerRecording();
      }, 90000);
    } catch {
      this.abortAnswerRecording();
      this.dataService.errorMessage.set('Unable to start spoken answer recording right now.');
    }
  }

  private async finishAnswerRecording(): Promise<void> {
    const sessionId = this.assessmentSessionId();
    if (!sessionId || !this.recordingAnswerAudio()) {
      return;
    }

    const chunks = this.answerAudioChunks.slice();
    const sampleRate = this.answerAudioSampleRate;
    this.abortAnswerRecording(false);

    if (chunks.length === 0) {
      this.dataService.errorMessage.set('No answer audio was captured. Please record again.');
      return;
    }

    try {
      this.transcribingAnswer.set(true);
      const audioFile = this.createAnswerAudioFile(chunks, sampleRate);
      const transcript = await this.dataService.transcribeAssessmentAnswer(sessionId, audioFile);
      this.applyTranscriptToAnswer(transcript);
    } catch {
      this.answerTranscript.set(null);
      this.answerTranscriptModel.set(null);
    } finally {
      this.transcribingAnswer.set(false);
    }
  }

  private applyTranscriptToAnswer(transcript: AssessmentSpeechTranscript): void {
    this.answerTranscript.set(transcript.transcript);
    this.answerTranscriptModel.set(transcript.model);
    this.answerDraft.set(transcript.transcript);
  }

  private createAnswerAudioFile(chunks: Float32Array[], sampleRate: number): File {
    const mergedLength = chunks.reduce((total, chunk) => total + chunk.length, 0);
    const merged = new Float32Array(mergedLength);
    let offset = 0;
    for (const chunk of chunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }

    const wavBuffer = this.encodeWavBuffer(merged, sampleRate);
    const blob = new Blob([wavBuffer], {type: 'audio/wav'});
    return new File([blob], `answer-${Date.now()}.wav`, {type: 'audio/wav'});
  }

  private encodeWavBuffer(samples: Float32Array, sampleRate: number): ArrayBuffer {
    const buffer = new ArrayBuffer(44 + (samples.length * 2));
    const view = new DataView(buffer);

    const writeString = (offset: number, value: string) => {
      for (let index = 0; index < value.length; index += 1) {
        view.setUint8(offset + index, value.charCodeAt(index));
      }
    };

    writeString(0, 'RIFF');
    view.setUint32(4, 36 + (samples.length * 2), true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, samples.length * 2, true);

    let offset = 44;
    for (let index = 0; index < samples.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, samples[index] ?? 0));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }

    return buffer;
  }

  private abortAnswerRecording(resetTranscript = false): void {
    if (this.answerRecordingTimer !== null) {
      window.clearInterval(this.answerRecordingTimer);
      this.answerRecordingTimer = null;
    }
    if (this.answerRecordingStopTimer !== null) {
      window.clearTimeout(this.answerRecordingStopTimer);
      this.answerRecordingStopTimer = null;
    }

    try {
      this.answerAudioSource?.disconnect();
      this.answerAudioProcessor?.disconnect();
    } catch {
      // Best effort cleanup for audio graph nodes.
    }

    if (this.answerAudioInputStream) {
      for (const track of this.answerAudioInputStream.getTracks()) {
        track.stop();
      }
      this.answerAudioInputStream = null;
    }

    if (this.answerAudioContext) {
      void this.answerAudioContext.close().catch(() => undefined);
      this.answerAudioContext = null;
    }

    this.answerAudioSource = null;
    this.answerAudioProcessor = null;
    this.answerAudioSink = null;
    this.recordingAnswerAudio.set(false);
    this.answerRecordingSeconds.set(0);

    if (resetTranscript) {
      this.answerTranscript.set(null);
      this.answerTranscriptModel.set(null);
      this.transcribingAnswer.set(false);
      this.answerAudioChunks = [];
    }
  }

  private stopPromptPlayback(): void {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }

  private async tryResumeAfterAntiSpoofDelay(
    sessionId: string,
    attempts = 6,
    delayMs = 2000,
  ): Promise<boolean> {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const status = await this.dataService.getAntiSpoofStatus(sessionId);
        this.antiSpoofStatus.set(status);
        if (this.isAntiSpoofPassed(status)) {
          await this.beginAssessmentQuestions();
          return true;
        }
      } catch {
        // Keep polling for a short period because anti-spoof analysis may still be finishing remotely.
      }

      if (attempt < attempts - 1) {
        await this.waitFor(delayMs);
      }
    }

    return false;
  }

  private waitFor(delayMs: number): Promise<void> {
    return new Promise((resolve) => {
      window.setTimeout(resolve, delayMs);
    });
  }

  private stopCamera(): void {
    this.abortAnswerRecording();

    if (this.activeRecorder && this.activeRecorder.state !== 'inactive') {
      this.activeRecorder.stop();
    }
    this.activeRecorder = null;

    if (this.mediaStream) {
      for (const track of this.mediaStream.getTracks()) {
        track.stop();
      }
      this.mediaStream = null;
    }
    if (this.previewStream) {
      for (const track of this.previewStream.getTracks()) {
        track.stop();
      }
      this.previewStream = null;
    }

    const preview = this.antiSpoofPreview?.nativeElement;
    if (preview) {
      preview.pause();
      preview.srcObject = null;
    }
    const assessmentPreview = this.assessmentPreview?.nativeElement;
    if (assessmentPreview) {
      assessmentPreview.pause();
      assessmentPreview.srcObject = null;
    }
    this.cameraReady.set(false);
    this.visionMonitoringAvailable.set(false);
  }

  private refreshPreviewStream(): void {
    if (this.previewStream) {
      for (const track of this.previewStream.getTracks()) {
        track.stop();
      }
      this.previewStream = null;
    }

    const sourceTrack = this.mediaStream?.getVideoTracks()[0];
    if (!sourceTrack) {
      return;
    }

    this.previewStream = new MediaStream([sourceTrack.clone()]);
  }

  private isAntiSpoofPassed(status: AntiSpoofStatus | null): boolean {
    if (!status) {
      return false;
    }

    if ((status.finalDecision ?? '').toUpperCase() === 'PASS') {
      return true;
    }

    const latest = (status.latestResultStatus ?? '').toUpperCase();
    const normalizedStatus = status.status.toLowerCase();
    return latest === 'PASS' && ['review_ready', 'finalized', 'locked'].includes(normalizedStatus);
  }

  private resetAnswerComposer(): void {
    this.abortAnswerRecording(true);
    this.answerDraft.set('');
  }

  private resetAssessmentState(): void {
    const existingUrl = this.recordedVideoUrl();
    if (existingUrl) {
      URL.revokeObjectURL(existingUrl);
    }

    this.cleanupAssessmentGuards();
    this.disconnectProctoringSocket();
    this.abortAnswerRecording(true);
    this.stopPromptPlayback();
    this.assessmentPhase.set('idle');
    this.examStarted.set(false);
    this.assessmentSessionId.set(null);
    this.assessmentJobId.set(null);
    this.assessmentWebsocketUrl.set('');
    this.assessmentQuestions.set([]);
    this.currentQuestion.set(1);
    this.answerDraft.set('');
    this.activeWarningDialog.set(null);
    this.warningDialogQueue.splice(0, this.warningDialogQueue.length);
    this.proctorCooldowns.clear();
    this.localGuardCooldowns.clear();
    this.lastTabSwitchAt = 0;
    this.gazeAwayStartedAt = null;
    this.visionCheckInFlight = false;

    this.antiSpoofSessionId.set('');
    this.antiSpoofStatus.set(null);
    this.antiSpoofChallenge.set(null);
    this.antiSpoofAnalysis.set(null);
    this.antiSpoofError.set(null);

    this.recordedVideoFile.set(null);
    this.recordedVideoUrl.set(null);
    this.cameraError.set(null);
    this.warningEvents.set([]);
    this.launchingAssessment.set(false);
    this.stopCamera();
  }
}
