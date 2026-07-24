import {AfterViewInit, Component, ElementRef, OnDestroy, ViewChild, computed, inject, signal} from '@angular/core';
import {MatIconModule} from '@angular/material/icon';
import {RouterLink} from '@angular/router';

import {AuthService} from '../../core/auth.service';

@Component({
  selector: 'app-face-register',
  standalone: true,
  imports: [MatIconModule, RouterLink],
  template: `
    <div class="auth-canvas flex min-h-screen items-center justify-center px-4 py-10">
      <div class="auth-card max-w-xl">
        <div class="space-y-6 p-8">
          <div class="text-center">
            <span class="auth-header-kicker">
              <mat-icon class="text-[16px]">looks_two</mat-icon>
              Candidate Flow Step 2
            </span>
            <div class="mt-4 flex items-center justify-center gap-2 font-bold tracking-tight text-primary-700">
              <mat-icon class="text-[30px]">face</mat-icon>
              <span class="text-2xl">Face Registration</span>
            </div>
            <p class="mt-2 text-sm text-slate-600">Capture a clear selfie so future logins can verify your identity.</p>
          </div>

          <div class="grid gap-2 text-xs sm:grid-cols-3">
            <div class="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-center font-semibold text-rose-700">1. Start Camera</div>
            <div class="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-center font-semibold text-rose-700">2. Capture Face</div>
            <div class="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-center font-semibold text-rose-700">3. Submit</div>
          </div>

          <div class="rounded-2xl border border-rose-100 bg-gradient-to-b from-rose-50 to-white p-6 space-y-4">
            <div class="rounded-xl border border-rose-100 bg-white p-3 text-xs text-slate-600">
              Keep your face centered, remove sunglasses, and use bright lighting.
            </div>

            <p class="block text-sm font-semibold text-slate-700">Camera Preview</p>

            <div class="relative flex aspect-video items-center justify-center overflow-hidden rounded-2xl bg-slate-900">
              <video #videoElement autoplay playsinline muted class="h-full w-full object-cover"></video>
              @if (!cameraReady()) {
                <div class="absolute text-xs text-slate-300">Camera not started</div>
              }
            </div>

            <div class="flex flex-wrap gap-2">
              <button
                type="button"
                (click)="startCamera()"
                class="w-full rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700 transition-colors hover:bg-rose-100 sm:w-auto"
              >
                Start Camera
              </button>

              <button
                type="button"
                (click)="captureFromCamera()"
                [disabled]="!cameraReady() || capturing()"
                class="w-full rounded-xl bg-primary-600 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
              >
                {{ capturing() ? 'Capturing...' : 'Capture Face' }}
              </button>

              <button
                type="button"
                (click)="retake()"
                [disabled]="!selectedFile()"
                class="w-full rounded-xl border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition-colors hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
              >
                Retake
              </button>
            </div>

            <div class="rounded-xl border border-rose-100 bg-white px-3 py-2 text-xs text-slate-600">
              @if (!cameraReady()) {
                Start your camera to begin face enrollment.
              } @else if (!selectedFile()) {
                Camera is live. Capture your face when you are ready.
              } @else {
                Face image captured. You can submit now or retake.
              }
            </div>

            @if (previewUrl()) {
              <div>
                <p class="mb-2 text-xs font-medium text-slate-500">Captured image</p>
                <img [src]="previewUrl()" alt="Face preview" class="h-40 w-40 rounded-2xl border border-rose-200 object-cover" />
              </div>
            }
          </div>

          @if (cameraError()) {
            <div class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {{ cameraError() }}
            </div>
          }

          @if (authService.errorMessage()) {
            <div class="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {{ authService.errorMessage() }}
            </div>
          }

          <button
            (click)="submit()"
            [disabled]="!selectedFile() || authService.loading()"
            class="auth-primary-button disabled:cursor-not-allowed disabled:opacity-50"
          >
            {{ authService.loading() ? 'Registering face...' : 'Register Face and Continue' }}
          </button>

          <div class="text-center">
            <a routerLink="/auth/login" class="text-sm font-medium text-slate-500 hover:text-primary-700">
              Back to login
            </a>
          </div>
        </div>
      </div>
    </div>
  `,
})
export class FaceRegisterComponent implements AfterViewInit, OnDestroy {
  @ViewChild('videoElement') private videoElement?: ElementRef<HTMLVideoElement>;

  authService = inject(AuthService);

  selectedFile = signal<File | null>(null);
  previewUrl = signal<string | null>(null);
  cameraReady = signal(false);
  cameraError = signal<string | null>(null);
  capturing = signal(false);

  private mediaStream: MediaStream | null = null;

  readonly canSubmit = computed(() => !!this.selectedFile() && !this.authService.loading());

  ngAfterViewInit(): void {
    void this.startCamera();
  }

  async startCamera(): Promise<void> {
    this.cameraError.set(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      this.cameraError.set('Camera access is not supported in this browser.');
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
        audio: false,
      });

      this.mediaStream = stream;
      const video = this.videoElement?.nativeElement;
      if (!video) {
        this.cameraError.set('Unable to initialize the camera preview.');
        this.stopCamera();
        return;
      }

      video.srcObject = stream;
      await video.play();
      this.cameraReady.set(true);
    } catch {
      this.cameraError.set('Camera permission denied or unavailable. Please allow camera access and retry.');
      this.stopCamera();
    }
  }

  async captureFromCamera(): Promise<void> {
    const video = this.videoElement?.nativeElement;
    if (!video || !this.cameraReady()) {
      this.cameraError.set('Start the camera before capturing a face.');
      return;
    }

    if (video.videoWidth === 0 || video.videoHeight === 0) {
      this.cameraError.set('Camera stream is not ready yet. Please try again.');
      return;
    }

    this.capturing.set(true);
    this.cameraError.set(null);

    try {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      const context = canvas.getContext('2d');
      if (!context) {
        this.cameraError.set('Unable to capture frame from camera.');
        return;
      }

      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      const blob = await new Promise<Blob | null>((resolve) => {
        canvas.toBlob(resolve, 'image/jpeg', 0.95);
      });

      if (!blob) {
        this.cameraError.set('Failed to capture face image. Please retry.');
        return;
      }

      this.selectedFile.set(new File([blob], `face-register-${Date.now()}.jpg`, {type: 'image/jpeg'}));
      this.previewUrl.set(canvas.toDataURL('image/jpeg', 0.9));
      this.stopCamera();
    } finally {
      this.capturing.set(false);
    }
  }

  retake(): void {
    this.selectedFile.set(null);
    this.previewUrl.set(null);
    void this.startCamera();
  }

  async submit(): Promise<void> {
    const file = this.selectedFile();
    if (!file || !this.canSubmit()) {
      return;
    }

    this.stopCamera();
    await this.authService.registerFace(file);
  }

  ngOnDestroy(): void {
    this.stopCamera();
  }

  private stopCamera(): void {
    if (this.mediaStream) {
      for (const track of this.mediaStream.getTracks()) {
        track.stop();
      }
      this.mediaStream = null;
    }

    const video = this.videoElement?.nativeElement;
    if (video) {
      video.srcObject = null;
    }
    this.cameraReady.set(false);
  }
}
