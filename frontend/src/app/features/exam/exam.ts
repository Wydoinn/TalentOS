import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';

import { AuthService } from '../../core/auth.service';
import { DataService, type CandidateSchedule, type ExamSlot } from '../../core/data.service';

interface CalendarDay {
  date: Date;
  isCurrentMonth: boolean;
  isToday: boolean;
  isSelected: boolean;
  isPast: boolean;
  hasAvailability: boolean;
  slotCount: number;
  isBookedDate: boolean;
}

@Component({
  selector: 'app-exam',
  standalone: true,
  imports: [MatIconModule, CommonModule, FormsModule],
  template: `
    <div class="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(254,205,211,0.55),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(191,219,254,0.6),_transparent_24%),linear-gradient(180deg,_#fff7fb_0%,_#fffdf8_42%,_#f8fbff_100%)] px-4 py-6 sm:px-6 lg:px-8">
      <div class="mx-auto max-w-7xl space-y-6 animate-in">
        <section class="grid gap-5 rounded-[2rem] border border-white/70 bg-[linear-gradient(135deg,_rgba(255,255,255,0.94),_rgba(255,244,247,0.92)_45%,_rgba(245,249,255,0.94)_100%)] p-6 shadow-[0_28px_90px_rgba(143,39,82,0.12)] xl:grid-cols-[minmax(0,1.2fr)_320px]">
          <div class="space-y-5">
            <div class="flex flex-wrap items-center gap-3">
              <span class="rounded-full border border-rose-200 bg-white/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700">Candidate Booking Portal</span>
              <span class="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">10-minute safety buffer</span>
            </div>
            <div class="max-w-3xl">
              <h1 class="font-['Space_Grotesk'] text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Choose the interview slot that fits your day.</h1>
              <p class="mt-3 max-w-2xl text-sm leading-6 text-slate-600 sm:text-base">This is a dedicated booking workspace. Pick a date, reserve a time, and TalentOS will sign you out safely after booking so your assessment link stays protected.</p>
            </div>
            <div class="grid gap-3 sm:grid-cols-3">
              <article class="rounded-[1.5rem] border border-white/70 bg-white/80 p-4">
                <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Open Slots</p>
                <p class="mt-2 text-3xl font-bold text-slate-900">{{ bookableSlots().length }}</p>
              </article>
              <article class="rounded-[1.5rem] border border-white/70 bg-white/80 p-4">
                <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Open Days This Month</p>
                <p class="mt-2 text-3xl font-bold text-slate-900">{{ availableDaysInMonth() }}</p>
              </article>
              <article class="rounded-[1.5rem] border border-white/70 bg-white/80 p-4">
                <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Next Opening</p>
                <p class="mt-2 text-sm font-semibold text-slate-900">{{ nextAvailableSlotLabel() }}</p>
              </article>
            </div>
          </div>

          <div class="flex flex-col justify-between rounded-[1.8rem] border border-white/10 bg-[linear-gradient(180deg,_rgba(17,24,39,0.95),_rgba(30,41,59,0.92))] p-5 text-white">
            <div>
              <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-200">Session Status</p>
              <p class="mt-3 text-2xl font-bold">{{ currentSchedule() ? 'Booked and ready' : 'Awaiting booking' }}</p>
              <p class="mt-2 text-sm leading-6 text-slate-300">{{ currentSchedule() ? formatScheduleWindow(currentSchedule()!) : 'Choose a slot below to receive your confirmation and assessment access email.' }}</p>
            </div>
            <button type="button" (click)="endSession()" class="mt-5 inline-flex items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/15">
              <mat-icon class="text-[18px]">logout</mat-icon>
              End Session
            </button>
          </div>
        </section>

        @if (bookingSuccess()) {
          <div class="rounded-[1.4rem] border border-emerald-200 bg-emerald-50/90 px-4 py-3 text-sm text-emerald-800">{{ bookingSuccess() }}</div>
        }

        @if (dataService.errorMessage()) {
          <div class="rounded-[1.4rem] border border-red-200 bg-red-50/95 px-4 py-3 text-sm text-red-700">{{ dataService.errorMessage() }}</div>
        }

        <div class="grid gap-6 xl:grid-cols-[minmax(0,1.28fr)_minmax(320px,0.92fr)]">
          <section class="rounded-[2rem] border border-white/70 bg-white/92 p-5 shadow-[0_20px_70px_rgba(143,39,82,0.1)] sm:p-6">
            <div class="flex flex-col gap-4 border-b border-rose-100 pb-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-600">Calendar</p>
                <h2 class="mt-2 font-['Space_Grotesk'] text-2xl font-bold text-slate-900">{{ formatMonthYear() }}</h2>
              </div>
              <div class="flex items-center gap-2">
                <button type="button" (click)="refreshSlots()" class="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-xs font-semibold uppercase tracking-[0.16em] text-rose-700 transition-colors hover:bg-rose-100">Refresh</button>
                <button type="button" (click)="prevMonth()" [disabled]="!canGoPrevMonth()" class="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"><mat-icon class="text-[20px]">chevron_left</mat-icon></button>
                <button type="button" (click)="nextMonth()" class="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-700"><mat-icon class="text-[20px]">chevron_right</mat-icon></button>
              </div>
            </div>

            <div class="mt-5 grid grid-cols-7 gap-2">
              @for (day of ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']; track day) {
                <div class="py-2 text-center text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">{{ day }}</div>
              }
            </div>

            <div class="grid grid-cols-7 gap-2">
              @for (day of calendarDays(); track day.date.getTime()) {
                <button
                  type="button"
                  (click)="selectDate(day)"
                  [disabled]="day.isPast"
                  class="relative aspect-square rounded-[1.25rem] border p-2 text-left transition-all"
                  [class.border-primary-500]="day.isSelected"
                  [class.bg-primary-600]="day.isSelected"
                  [class.text-white]="day.isSelected"
                  [class.border-amber-300]="day.isBookedDate && !day.isSelected"
                  [class.bg-amber-50]="day.isBookedDate && !day.isSelected"
                  [class.border-slate-200]="!day.isSelected && !day.isBookedDate"
                  [class.bg-white]="!day.isSelected && !day.isBookedDate"
                  [class.opacity-55]="!day.isCurrentMonth && !day.isSelected"
                  [class.cursor-not-allowed]="day.isPast"
                >
                  <div class="flex h-full flex-col justify-between">
                    <div class="flex items-start justify-between gap-2">
                      <span class="inline-flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold" [class.bg-white/15]="day.isSelected" [class.bg-slate-100]="!day.isSelected && !day.isBookedDate" [class.bg-amber-100]="day.isBookedDate && !day.isSelected" [class.text-slate-900]="!day.isSelected">{{ day.date.getDate() }}</span>
                      @if (day.slotCount > 0 && !day.isSelected) {
                        <span class="rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-700">{{ day.slotCount }}</span>
                      }
                    </div>
                    <div class="space-y-1">
                      @if (day.isToday && !day.isSelected) {
                        <p class="text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-600">Today</p>
                      }
                      @if (day.isBookedDate && !day.isSelected) {
                        <p class="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-700">Booked</p>
                      }
                      <div class="flex items-center gap-1.5">
                        @if (day.hasAvailability) {
                          <span class="h-2 w-2 rounded-full" [class.bg-emerald-500]="!day.isSelected" [class.bg-white]="day.isSelected"></span>
                        }
                        <span class="text-[10px]" [class.text-white/90]="day.isSelected" [class.text-slate-500]="!day.isSelected">{{ day.hasAvailability ? 'Available' : (day.isPast ? 'Closed' : 'No slots') }}</span>
                      </div>
                    </div>
                  </div>
                </button>
              }
            </div>
          </section>

          <section class="space-y-5 rounded-[2rem] border border-white/70 bg-white/92 p-5 shadow-[0_20px_70px_rgba(39,67,143,0.1)] sm:p-6">
            @if (currentSchedule(); as schedule) {
              <div class="rounded-[1.6rem] border border-amber-200 bg-[linear-gradient(180deg,_#fffdf7_0%,_#fff7ed_100%)] p-4">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700">Current Booking</p>
                    <h2 class="mt-2 text-xl font-bold text-slate-900">{{ formatScheduleDate(schedule) }}</h2>
                    <p class="mt-1 text-sm text-slate-600">{{ formatScheduleWindow(schedule) }}</p>
                  </div>
                  <span class="rounded-full border border-amber-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-700">{{ schedule.status }}</span>
                </div>
                <button type="button" (click)="toggleReschedule()" class="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-primary-200 bg-white px-4 py-3 text-sm font-semibold text-primary-700 transition-colors hover:bg-primary-50">
                  <mat-icon class="text-[18px]">edit_calendar</mat-icon>
                  {{ rescheduleMode() ? 'Exit Reschedule Mode' : 'Reschedule This Slot' }}
                </button>
                <textarea [(ngModel)]="cancellationReason" rows="3" placeholder="Optional reason for cancelling" class="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 outline-none transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/15"></textarea>
                <button type="button" (click)="cancelCurrentSchedule()" [disabled]="bookingInProgress()" class="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50">
                  <mat-icon class="text-[18px]">cancel</mat-icon>
                  {{ bookingInProgress() ? actionLabel() : 'Cancel Slot' }}
                </button>
              </div>
            }

            <div class="rounded-[1.6rem] border border-slate-200 bg-[linear-gradient(180deg,_#ffffff_0%,_#f8fbff_100%)] p-4">
              <p class="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-700">Selected Day</p>
              <h2 class="mt-2 text-2xl font-bold text-slate-900">{{ selectedDate() ? formatSelectedDate() : 'Choose a date from the calendar' }}</h2>
              <p class="mt-1 text-sm text-slate-600">{{ selectedDate() ? selectedDateSummary() : 'Available times will appear here as soon as you choose a date.' }}</p>

              @if (selectedDate()) {
                <div class="mt-5 grid gap-3">
                  @for (slot of selectedDateSlots(); track slot.date + slot.time + (slot.slotId || '')) {
                    <button
                      type="button"
                      (click)="selectSlot(slot)"
                      class="flex items-center justify-between gap-4 rounded-[1.3rem] border px-4 py-4 text-left transition-all"
                      [class.border-primary-500]="selectedSlot() === slot"
                      [class.bg-primary-50]="selectedSlot() === slot"
                      [class.border-slate-200]="selectedSlot() !== slot"
                      [class.bg-white]="selectedSlot() !== slot"
                    >
                      <div>
                        <p class="text-base font-semibold text-slate-900">{{ slot.time }}</p>
                        <p class="mt-1 text-sm text-slate-500">{{ selectedSlotMeta(slot) }}</p>
                      </div>
                      @if (selectedSlot() === slot) {
                        <span class="rounded-full bg-primary-600 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-white">Selected</span>
                      }
                    </button>
                  } @empty {
                    <div class="rounded-[1.3rem] border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500">No eligible slots are open for this date.</div>
                  }
                </div>
              }

              <div class="mt-5 rounded-[1.3rem] border border-slate-200 bg-white p-4">
                <p class="text-sm leading-6 text-slate-500">{{ currentSchedule() && !rescheduleMode() ? 'You already have a booked slot. Turn on reschedule mode to replace it.' : 'Booking confirms your slot, sends the access email, and ends this session for security.' }}</p>
                <button type="button" (click)="bookSlot()" [disabled]="!selectedSlot() || bookingInProgress() || (currentSchedule() && !rescheduleMode())" class="mt-4 inline-flex w-full items-center justify-center rounded-2xl bg-primary-600 px-6 py-3 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50">
                  {{ bookingInProgress() ? actionLabel() : submitLabel() }}
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  `,
})
export class ExamComponent implements OnInit {
  dataService = inject(DataService);
  authService = inject(AuthService);

  bookingInProgress = signal(false);
  bookingSuccess = signal<string | null>(null);
  rescheduleMode = signal(false);
  actionLabel = signal('Processing...');
  cancellationReason = '';

  currentDate = signal(new Date());
  calendarDays = signal<CalendarDay[]>([]);
  selectedDate = signal<Date | null>(null);
  selectedSlot = signal<ExamSlot | null>(null);

  currentSchedule = computed(
    () => this.dataService.candidateSchedules().find((schedule) => schedule.status === 'BOOKED' || schedule.status === 'RESCHEDULED') ?? null,
  );
  bookableSlots = computed(() =>
    [...this.dataService.availableExamSlots()]
      .filter((slot) => this.isSlotBookable(slot))
      .sort((left, right) => this.slotStartsAt(left) - this.slotStartsAt(right)),
  );
  selectedDateSlots = computed(() => {
    const selected = this.selectedDate();
    if (!selected) {
      return [];
    }

    const selectedIso = this.toLocalDateKey(selected);
    return this.bookableSlots()
      .filter((slot) => slot.date === selectedIso)
      .filter((slot) => !this.currentSchedule() || slot.slotId !== this.currentSchedule()?.slotId);
  });
  availableDaysInMonth = computed(() => {
    const month = this.currentDate().getMonth();
    const year = this.currentDate().getFullYear();
    return new Set(
      this.bookableSlots()
        .filter((slot) => {
          const parsed = this.slotDate(slot);
          return parsed.getFullYear() === year && parsed.getMonth() === month;
        })
        .map((slot) => slot.date),
    ).size;
  });

  ngOnInit(): void {
    void this.initialize();
  }

  async initialize(): Promise<void> {
    await this.dataService.loadCandidateSchedules();
    await this.refreshSlots();

    const current = this.currentSchedule();
    if (current) {
      const start = new Date(current.slotStartAt);
      if (!Number.isNaN(start.getTime())) {
        this.selectedDate.set(start);
        this.currentDate.set(new Date(start.getFullYear(), start.getMonth(), 1));
      }
    }

    this.generateCalendar();
  }

  async refreshSlots(): Promise<void> {
    await this.dataService.loadAvailableSlots();

    if (!this.selectedDate()) {
      const firstSlot = this.bookableSlots()[0];
      if (firstSlot) {
        this.selectedDate.set(this.slotDate(firstSlot));
      }
    }

    this.generateCalendar();
  }

  generateCalendar(): void {
    const year = this.currentDate().getFullYear();
    const month = this.currentDate().getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const days: CalendarDay[] = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const bookedDateKey = this.currentBookedDateKey();
    const firstDayOfWeek = firstDay.getDay();
    const prevMonthLastDay = new Date(year, month, 0).getDate();

    for (let i = firstDayOfWeek - 1; i >= 0; i--) {
      const date = new Date(year, month - 1, prevMonthLastDay - i);
      const slotCount = this.slotCountForDate(date);
      days.push({ date, isCurrentMonth: false, isToday: date.getTime() === today.getTime(), isSelected: this.selectedDate()?.getTime() === date.getTime(), isPast: date.getTime() < today.getTime(), hasAvailability: slotCount > 0, slotCount, isBookedDate: bookedDateKey === this.toLocalDateKey(date) });
    }

    for (let i = 1; i <= lastDay.getDate(); i++) {
      const date = new Date(year, month, i);
      const slotCount = this.slotCountForDate(date);
      days.push({ date, isCurrentMonth: true, isToday: date.getTime() === today.getTime(), isSelected: this.selectedDate()?.getTime() === date.getTime(), isPast: date.getTime() < today.getTime(), hasAvailability: slotCount > 0, slotCount, isBookedDate: bookedDateKey === this.toLocalDateKey(date) });
    }

    const remainingDays = 42 - days.length;
    for (let i = 1; i <= remainingDays; i++) {
      const date = new Date(year, month + 1, i);
      const slotCount = this.slotCountForDate(date);
      days.push({ date, isCurrentMonth: false, isToday: date.getTime() === today.getTime(), isSelected: this.selectedDate()?.getTime() === date.getTime(), isPast: date.getTime() < today.getTime(), hasAvailability: slotCount > 0, slotCount, isBookedDate: bookedDateKey === this.toLocalDateKey(date) });
    }

    this.calendarDays.set(days);
  }

  nextMonth(): void {
    const next = new Date(this.currentDate());
    next.setMonth(next.getMonth() + 1);
    this.currentDate.set(next);
    this.generateCalendar();
  }

  prevMonth(): void {
    if (!this.canGoPrevMonth()) {
      return;
    }
    const prev = new Date(this.currentDate());
    prev.setMonth(prev.getMonth() - 1);
    this.currentDate.set(prev);
    this.generateCalendar();
  }

  selectDate(day: CalendarDay): void {
    if (day.isPast) {
      return;
    }
    this.selectedDate.set(day.date);
    this.selectedSlot.set(null);
    this.bookingSuccess.set(null);
    this.generateCalendar();
  }

  formatMonthYear(): string {
    return this.currentDate().toLocaleString('default', { month: 'long', year: 'numeric' });
  }

  formatSelectedDate(): string {
    const date = this.selectedDate();
    if (!date) {
      return '';
    }
    return date.toLocaleString('default', { weekday: 'long', month: 'long', day: 'numeric' });
  }

  selectedDateSummary(): string {
    const slotCount = this.selectedDateSlots().length;
    if (slotCount === 0) {
      return 'No eligible time slots are open for this date yet.';
    }
    return `${slotCount} ${slotCount === 1 ? 'time slot is' : 'time slots are'} currently open for booking.`;
  }

  formatScheduleDate(schedule: CandidateSchedule): string {
    const start = new Date(schedule.slotStartAt);
    if (Number.isNaN(start.getTime())) {
      return schedule.slotStartAt;
    }
    return start.toLocaleString('default', { weekday: 'long', month: 'short', day: 'numeric' });
  }

  formatScheduleWindow(schedule: CandidateSchedule): string {
    const start = new Date(schedule.slotStartAt);
    const end = new Date(schedule.slotEndAt);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return schedule.timezone;
    }
    return `${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} (${schedule.timezone})`;
  }

  selectSlot(slot: ExamSlot): void {
    this.selectedSlot.set(slot);
    this.bookingSuccess.set(null);
  }

  toggleReschedule(): void {
    this.rescheduleMode.update((value) => !value);
    this.bookingSuccess.set(null);
  }

  async bookSlot(): Promise<void> {
    const slot = this.selectedSlot();
    const date = this.selectedDate();
    if (!slot || !date) {
      return;
    }

    try {
      this.bookingInProgress.set(true);
      this.bookingSuccess.set(null);
      const activeSchedule = this.currentSchedule();
      if (activeSchedule && this.rescheduleMode()) {
        this.actionLabel.set('Rescheduling...');
        await this.dataService.rescheduleCandidateSchedule(activeSchedule.scheduleId, slot.slotId || '');
        await this.refreshSlots();
        this.rescheduleMode.set(false);
        this.bookingSuccess.set('Your assessment slot was updated and a refreshed confirmation email has been sent.');
        return;
      }

      this.actionLabel.set('Booking...');
      await this.dataService.scheduleExam({ ...slot, date: this.toLocalDateKey(date) });
      this.bookingSuccess.set('Slot booked successfully. Your confirmation and separate L0 access email have been sent. Signing out for security.');
      await this.authService.logout();
    } catch {
      // DataService exposes the API message via errorMessage.
    } finally {
      this.bookingInProgress.set(false);
      this.actionLabel.set('Processing...');
    }
  }

  async cancelCurrentSchedule(): Promise<void> {
    const schedule = this.currentSchedule();
    if (!schedule) {
      return;
    }

    try {
      this.bookingInProgress.set(true);
      this.actionLabel.set('Cancelling...');
      this.bookingSuccess.set(null);
      await this.dataService.cancelSchedule(schedule.scheduleId, this.cancellationReason);
      this.cancellationReason = '';
      this.rescheduleMode.set(false);
      this.selectedSlot.set(null);
      await this.refreshSlots();
      this.bookingSuccess.set('Your booked slot was cancelled. You can now choose a new slot.');
    } catch {
      // DataService exposes the API message via errorMessage.
    } finally {
      this.bookingInProgress.set(false);
      this.actionLabel.set('Processing...');
    }
  }

  submitLabel(): string {
    return this.currentSchedule() && this.rescheduleMode() ? 'Confirm Reschedule' : 'Book Selected Slot';
  }

  async endSession(): Promise<void> {
    this.bookingSuccess.set(null);
    await this.authService.logout();
  }

  canGoPrevMonth(): boolean {
    const today = new Date();
    const currentMonthStart = new Date(today.getFullYear(), today.getMonth(), 1);
    const visibleMonthStart = new Date(this.currentDate().getFullYear(), this.currentDate().getMonth(), 1);
    return visibleMonthStart.getTime() > currentMonthStart.getTime();
  }

  selectedSlotMeta(slot: ExamSlot): string {
    const parts = [this.slotTimeRange(slot)];
    if (slot.timezone?.trim()) {
      parts.push(slot.timezone.trim());
    }
    return parts.join(' • ');
  }

  nextAvailableSlotLabel(): string {
    const slot = this.bookableSlots()[0];
    if (!slot) {
      return 'No open slots published yet.';
    }
    const start = this.slotDate(slot);
    return start.toLocaleString('default', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  private isSlotBookable(slot: ExamSlot): boolean {
    if (!slot.startAt) {
      return true;
    }
    const start = new Date(slot.startAt);
    if (Number.isNaN(start.getTime())) {
      return false;
    }
    return start.getTime() > Date.now() + (10 * 60 * 1000);
  }

  private toLocalDateKey(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private slotStartsAt(slot: ExamSlot): number {
    const parsed = slot.startAt ? new Date(slot.startAt) : this.slotDate(slot);
    const value = parsed.getTime();
    return Number.isNaN(value) ? Number.MAX_SAFE_INTEGER : value;
  }

  private slotDate(slot: ExamSlot): Date {
    if (slot.startAt) {
      const start = new Date(slot.startAt);
      if (!Number.isNaN(start.getTime())) {
        return start;
      }
    }
    return new Date(`${slot.date}T00:00:00`);
  }

  private slotCountForDate(date: Date): number {
    const key = this.toLocalDateKey(date);
    return this.bookableSlots()
      .filter((slot) => slot.date === key)
      .filter((slot) => !this.currentSchedule() || slot.slotId !== this.currentSchedule()?.slotId)
      .length;
  }

  private slotTimeRange(slot: ExamSlot): string {
    const start = slot.startAt ? new Date(slot.startAt) : null;
    const end = slot.endAt ? new Date(slot.endAt) : null;
    if (!start || !end || Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      return slot.time;
    }
    return `${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  }

  private currentBookedDateKey(): string | null {
    const current = this.currentSchedule();
    if (!current) {
      return null;
    }
    const start = new Date(current.slotStartAt);
    if (Number.isNaN(start.getTime())) {
      return null;
    }
    return this.toLocalDateKey(start);
  }
}
