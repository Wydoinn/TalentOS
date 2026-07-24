import {Component, signal, ViewChild, ElementRef, AfterViewChecked, inject, OnInit} from '@angular/core';
import {MatIconModule} from '@angular/material/icon';
import {FormsModule} from '@angular/forms';
import {CommonModule} from '@angular/common';

import {AssistantService, type ChatMessage} from '../../core/assistant.service';
import {DataService} from '../../core/data.service';
import {AuthService} from '../../core/auth.service';

interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [MatIconModule, FormsModule, CommonModule],
  template: `
    <div class="page-shell animate-in">
      <section class="page-hero p-6">
        <div class="relative flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span class="brand-chip">HireAgent Console</span>
            <h1 class="mt-4 font-['Space_Grotesk'] text-3xl font-bold">Ask TalentOS about candidates, pipeline health, and hiring actions.</h1>
            <p class="mt-3 max-w-2xl text-sm leading-7 text-white/82">
              HireAgent uses backend-orchestrated Gemini responses with live platform context so teams can ask workflow questions without leaving the app.
            </p>
          </div>
          <div class="glass-panel px-4 py-4">
            <p class="text-xs font-semibold uppercase tracking-[0.16em] text-white/72">Live Context</p>
            <p class="mt-2 text-lg font-semibold text-white">{{ authService.currentUser()?.role === 'pm' ? 'Roles, rankings, and reports' : 'Assessment and onboarding status' }}</p>
          </div>
        </div>
      </section>

      <div class="surface-card flex h-[calc(100vh-16rem)] min-h-[36rem] flex-col overflow-hidden">

      <!-- Header -->
      <div class="flex items-center justify-between border-b border-[var(--brand-line)] bg-[linear-gradient(180deg,rgba(121,47,140,0.04),rgba(166,37,104,0.02))] p-5">
        <div class="flex items-center gap-3">
          <div class="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-primary-500 via-primary-600 to-primary-700 text-white shadow-[0_18px_32px_rgba(166,37,104,0.24)]">
            <mat-icon>smart_toy</mat-icon>
          </div>
          <div>
            <h2 class="font-semibold text-[var(--brand-ink)]">HireAgent</h2>
            <p class="flex items-center gap-1 text-xs text-[var(--brand-berry)]">
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]"></span>
              AI-Powered · Gemini
            </p>
          </div>
        </div>
        <button (click)="clearChat()" class="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-500 transition-colors px-3 py-1.5 rounded-lg hover:bg-red-50">
          <mat-icon class="text-[16px]">delete_outline</mat-icon>
          Clear
        </button>
      </div>

      <!-- Messages -->
      <div class="flex-1 overflow-y-auto p-6 space-y-6" #scrollContainer>
        @if (messages().length === 0) {
          <div class="h-full flex flex-col items-center justify-center text-center p-6">
            <div class="mb-5 flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-50 to-primary-50 text-primary-700 shadow-inner">
              <mat-icon class="text-[40px]">auto_awesome</mat-icon>
            </div>
            <h3 class="text-xl font-bold text-gray-900 mb-2">How can I help you?</h3>
            <p class="text-sm text-gray-500 max-w-md mb-8">
              I'm HireAgent — your AI hiring assistant. Ask me about candidates, pipeline insights, or draft interview emails.
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
              @for (suggestion of suggestions; track suggestion) {
                <button (click)="sendPrompt(suggestion)"
                  class="group rounded-xl border border-rose-200 p-4 text-left text-sm text-gray-700 transition-all hover:border-primary-400 hover:bg-rose-50">
                  <span class="text-primary-500 mr-2">›</span>{{ suggestion }}
                </button>
              }
            </div>
          </div>
        }

        @for (msg of messages(); track msg.id) {
          <div class="flex gap-3" [class.flex-row-reverse]="msg.role === 'user'">
            <!-- Avatar -->
            <div class="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-1"
                 [class]="msg.role === 'assistant'
                   ? 'bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-sm'
                   : 'bg-gray-200'">
              @if (msg.role === 'assistant') {
                <mat-icon class="text-[16px]">smart_toy</mat-icon>
              } @else {
                <mat-icon class="text-[16px] text-gray-600">person</mat-icon>
              }
            </div>

            <!-- Bubble -->
            <div class="max-w-[75%] flex flex-col gap-1" [class.items-end]="msg.role === 'user'">
              <div [class]="msg.role === 'assistant'
                ? 'bg-gray-50 border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 text-gray-900 text-sm leading-relaxed'
                : 'bg-primary-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed'">
                @if (msg.isStreaming) {
                  <span class="inline-flex gap-1 items-center">
                    <span class="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:0ms]"></span>
                    <span class="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]"></span>
                    <span class="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:300ms]"></span>
                  </span>
                } @else {
                  <div [innerHTML]="renderMarkdown(msg.content)"></div>
                }
              </div>
              <span class="text-[10px] text-gray-400 px-1">
                {{ msg.timestamp | date:'h:mm a' }}
              </span>
            </div>
          </div>
        }
      </div>

      <!-- Input -->
      <div class="border-t border-rose-100 bg-rose-50/40 p-4">
        <div class="flex gap-3 items-end">
          <textarea
            [(ngModel)]="inputText"
            (keydown.enter)="onEnterKey($event)"
            placeholder="Ask about candidates, pipeline, or draft an email..."
            rows="1"
            class="max-h-32 flex-1 resize-none rounded-xl border border-rose-200 bg-white px-4 py-3 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/30"
            [disabled]="isLoading()">
          </textarea>
          <button
            (click)="sendMessage()"
            [disabled]="!inputText.trim() || isLoading()"
            class="w-11 h-11 bg-primary-600 hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl flex items-center justify-center transition-all shadow-sm shadow-primary-500/30 hover:shadow-md hover:shadow-primary-500/30 shrink-0">
            @if (isLoading()) {
              <mat-icon class="text-[20px] animate-spin">progress_activity</mat-icon>
            } @else {
              <mat-icon class="text-[20px]">send</mat-icon>
            }
          </button>
        </div>
        <p class="text-[10px] text-gray-400 mt-2 text-center">
          Powered by Gemini AI · Press Enter to send, Shift+Enter for new line
        </p>
      </div>
      </div>
    </div>
  `,
})
export class ChatComponent implements AfterViewChecked, OnInit {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  private assistantService = inject(AssistantService);
  private dataService = inject(DataService);
  authService = inject(AuthService);

  messages = signal<DisplayMessage[]>([]);
  inputText = '';
  isLoading = signal(false);

  suggestions = [
    'Who are the top candidates for open roles?',
    'Give me a pipeline summary',
    'Draft an interview invitation email',
    'What roles need immediate attention?',
  ];

  ngOnInit(): void {
    // Pre-load data context
    this.dataService.loadJobs();
    if (this.authService.currentUser()?.role === 'pm') {
      this.dataService.refreshCandidates();
    }
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  onEnterKey(event: Event): void {
    const keyboardEvent = event as KeyboardEvent;
    if (!keyboardEvent.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  async sendPrompt(text: string): Promise<void> {
    this.inputText = text;
    await this.sendMessage();
  }

  async sendMessage(): Promise<void> {
    const text = this.inputText.trim();
    if (!text || this.isLoading()) return;

    this.inputText = '';
    const userMsg: DisplayMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    const thinkingMsg: DisplayMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    };

    this.messages.update(msgs => [...msgs, userMsg, thinkingMsg]);
    this.isLoading.set(true);

    // Build history from current messages for context
    const history: ChatMessage[] = this.messages()
      .filter(m => !m.isStreaming && m.id !== thinkingMsg.id)
      .slice(-10)
      .map(m => ({role: m.role, content: m.content}));

    try {
      const reply = await this.assistantService.answer(text, history);
      this.messages.update(msgs =>
        msgs.map(m => m.id === thinkingMsg.id ? {...m, content: reply, isStreaming: false} : m)
      );
    } catch {
      this.messages.update(msgs =>
        msgs.map(m => m.id === thinkingMsg.id
          ? {...m, content: 'Sorry, I encountered an error. Please try again.', isStreaming: false}
          : m
        )
      );
    } finally {
      this.isLoading.set(false);
    }
  }

  clearChat(): void {
    this.messages.set([]);
  }

  renderMarkdown(text: string): string {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
      .replace(/(<li.*<\/li>\n?)+/g, '<ul class="space-y-1 my-2">$&</ul>')
      .replace(/\n/g, '<br>');
  }

  private scrollToBottom(): void {
    try {
      const el = this.scrollContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch {}
  }
}
