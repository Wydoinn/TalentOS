import {Component, signal, ViewChild, ElementRef, AfterViewChecked, inject} from '@angular/core';
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
  selector: 'app-chat-widget',
  standalone: true,
  imports: [MatIconModule, FormsModule, CommonModule],
  template: `
    <!-- FAB -->
    <button
      (click)="toggleChat()"
      class="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl focus:outline-none focus:ring-4 focus:ring-primary-500/30">
      <mat-icon class="text-2xl">{{ isOpen() ? 'close' : 'chat' }}</mat-icon>
    </button>

    <!-- Chat Window -->
    @if (isOpen()) {
      <div class="fixed bottom-24 right-3 z-50 flex h-[520px] max-h-[calc(100vh-120px)] w-[calc(100vw-1.5rem)] max-w-[400px] flex-col overflow-hidden rounded-2xl border border-rose-100 bg-white shadow-2xl sm:right-6">

        <!-- Header -->
        <div class="flex items-center justify-between border-b border-rose-100 bg-gradient-to-r from-rose-50 to-white p-4">
          <div class="flex items-center gap-3">
            <div class="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-primary-500 to-primary-700 text-white shadow-sm">
              <mat-icon class="text-[18px]">smart_toy</mat-icon>
            </div>
            <div>
              <h2 class="font-semibold text-sm text-gray-900">HireAgent</h2>
              <p class="flex items-center gap-1 text-[10px] text-rose-700">
                <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-600"></span>
                AI-Powered · Gemini
              </p>
            </div>
          </div>
          <button (click)="toggleChat()" class="p-1.5 text-gray-400 hover:text-gray-600 transition-colors rounded-lg hover:bg-gray-100">
            <mat-icon class="text-[18px]">close</mat-icon>
          </button>
        </div>

        <!-- Messages -->
        <div class="flex-1 overflow-y-auto p-4 space-y-4" #scrollContainer>
          @if (messages().length === 0) {
            <div class="h-full flex flex-col items-center justify-center text-center p-4">
              <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-50 to-primary-50 text-primary-700">
                <mat-icon class="text-[28px]">auto_awesome</mat-icon>
              </div>
              <h3 class="text-sm font-bold text-gray-900 mb-1">Ask HireAgent</h3>
              <p class="text-xs text-gray-500 mb-4">AI-powered hiring insights</p>
              <div class="flex flex-col gap-2 w-full">
                @for (s of quickSuggestions; track s) {
                  <button (click)="sendPrompt(s)"
                    class="rounded-lg border border-rose-200 px-3 py-2 text-left text-xs text-gray-700 transition-all hover:border-primary-400 hover:bg-rose-50">
                    <span class="text-primary-500">›</span> {{ s }}
                  </button>
                }
              </div>
            </div>
          }

          @for (msg of messages(); track msg.id) {
            <div class="flex gap-2" [class.flex-row-reverse]="msg.role === 'user'">
              <div class="w-6 h-6 rounded-full flex items-center justify-center shrink-0 mt-1"
                   [class]="msg.role === 'assistant' ? 'bg-gradient-to-br from-primary-500 to-primary-700 text-white' : 'bg-gray-200'">
                <mat-icon class="text-[12px]">{{ msg.role === 'assistant' ? 'smart_toy' : 'person' }}</mat-icon>
              </div>
              <div class="max-w-[80%]" [class.text-right]="msg.role === 'user'">
                <div [class]="msg.role === 'assistant'
                  ? 'bg-gray-50 border border-gray-100 rounded-2xl rounded-tl-sm px-3 py-2.5 text-xs text-gray-900 leading-relaxed'
                  : 'bg-primary-600 text-white rounded-2xl rounded-tr-sm px-3 py-2.5 text-xs leading-relaxed'">
                  @if (msg.isStreaming) {
                    <span class="inline-flex gap-1 items-center">
                      <span class="w-1 h-1 rounded-full bg-gray-400 animate-bounce [animation-delay:0ms]"></span>
                      <span class="w-1 h-1 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]"></span>
                      <span class="w-1 h-1 rounded-full bg-gray-400 animate-bounce [animation-delay:300ms]"></span>
                    </span>
                  } @else {
                    <div [innerHTML]="renderMarkdown(msg.content)"></div>
                  }
                </div>
              </div>
            </div>
          }
        </div>

        <!-- Input -->
        <div class="border-t border-rose-100 bg-rose-50/40 p-3">
          <div class="flex gap-2 items-center">
            <input
              [(ngModel)]="inputText"
              (keydown.enter)="sendMessage()"
              placeholder="Ask about candidates..."
              class="flex-1 rounded-xl border border-rose-200 bg-white px-3 py-2.5 text-xs text-gray-900 placeholder-gray-400 transition-all focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/30"
              [disabled]="isLoading()" />
            <button
              (click)="sendMessage()"
              [disabled]="!inputText.trim() || isLoading()"
              class="w-9 h-9 bg-primary-600 hover:bg-primary-700 disabled:opacity-40 text-white rounded-xl flex items-center justify-center transition-all shrink-0">
              @if (isLoading()) {
                <mat-icon class="text-[16px] animate-spin">progress_activity</mat-icon>
              } @else {
                <mat-icon class="text-[16px]">send</mat-icon>
              }
            </button>
          </div>
        </div>
      </div>
    }
  `,
})
export class ChatWidgetComponent implements AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  private assistantService = inject(AssistantService);
  private dataService = inject(DataService);
  private authService = inject(AuthService);

  isOpen = signal(false);
  messages = signal<DisplayMessage[]>([]);
  inputText = '';
  isLoading = signal(false);

  quickSuggestions = [
    'Show top candidates',
    'Pipeline trends',
    'Draft invite email',
    'Roles needing attention',
  ];

  toggleChat(): void {
    this.isOpen.update(v => !v);
    if (this.isOpen()) {
      this.dataService.loadJobs();
      if (this.authService.currentUser()?.role === 'pm') {
        this.dataService.refreshCandidates();
      }
    }
  }

  ngAfterViewChecked(): void {
    try {
      const el = this.scrollContainer?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch {}
  }

  async sendPrompt(text: string): Promise<void> {
    this.inputText = text;
    await this.sendMessage();
  }

  async sendMessage(): Promise<void> {
    const text = this.inputText.trim();
    if (!text || this.isLoading()) return;

    this.inputText = '';
    const userMsg: DisplayMessage = {id: crypto.randomUUID(), role: 'user', content: text, timestamp: new Date()};
    const thinkingMsg: DisplayMessage = {id: crypto.randomUUID(), role: 'assistant', content: '', timestamp: new Date(), isStreaming: true};

    this.messages.update(msgs => [...msgs, userMsg, thinkingMsg]);
    this.isLoading.set(true);

    const history: ChatMessage[] = this.messages()
      .filter(m => !m.isStreaming && m.id !== thinkingMsg.id)
      .slice(-6)
      .map(m => ({role: m.role, content: m.content}));

    try {
      const reply = await this.assistantService.answer(text, history);
      this.messages.update(msgs =>
        msgs.map(m => m.id === thinkingMsg.id ? {...m, content: reply, isStreaming: false} : m)
      );
    } catch {
      this.messages.update(msgs =>
        msgs.map(m => m.id === thinkingMsg.id ? {...m, content: 'Sorry, something went wrong.', isStreaming: false} : m)
      );
    } finally {
      this.isLoading.set(false);
    }
  }

  renderMarkdown(text: string): string {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/^- (.+)$/gm, '<li class="ml-3 list-disc">$1</li>')
      .replace(/(<li.*<\/li>\n?)+/g, '<ul class="my-1">$&</ul>')
      .replace(/\n/g, '<br>');
  }
}
