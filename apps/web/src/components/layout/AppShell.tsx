import {
  Bot,
  CreditCard,
  LayoutDashboard,
  Menu,
  Repeat2,
  Settings,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  type PropsWithChildren,
  type RefObject,
} from 'react';

import { ApiFoundationStatus } from './ApiFoundationStatus';
import { Brand } from './Brand';
import {
  useFoundationStatus,
  type FoundationStatus,
} from '../../graphql/foundation-status';

interface NavigationItem {
  readonly label: string;
  readonly href?: string;
  readonly icon: LucideIcon;
  readonly current?: boolean;
}

const navigationItems: readonly NavigationItem[] = [
  {
    label: 'Overview',
    href: '#overview',
    icon: LayoutDashboard,
    current: true,
  },
  { label: 'Transactions', href: '#transactions', icon: CreditCard },
  { label: 'People', icon: Users },
  { label: 'Recurring', icon: Repeat2 },
  { label: 'AI preview', href: '#assistant', icon: Bot },
];

interface SidebarProps {
  readonly foundationStatus: FoundationStatus;
  readonly onNavigate?: () => void;
}

function Sidebar({ foundationStatus, onNavigate }: SidebarProps) {
  return (
    <div className="bg-ink-900 flex h-full flex-col text-white">
      <div className="flex h-[76px] items-center border-b border-white/15 px-5">
        <Brand />
      </div>

      <nav className="flex-1 px-3 py-6" aria-label="Primary navigation">
        <p className="mb-2 px-3 text-[10px] font-semibold tracking-[0.18em] text-white/70 uppercase">
          Workspace
        </p>
        <ul className="space-y-1">
          {navigationItems.map((item) => {
            const Icon = item.icon;
            const content = (
              <>
                <Icon
                  className={
                    item.current ? 'text-leaf-200 size-[18px]' : 'size-[18px]'
                  }
                  strokeWidth={1.8}
                  aria-hidden="true"
                />
                {item.label}
                {!item.href && (
                  <span className="ml-auto rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold text-white/75">
                    Soon
                  </span>
                )}
              </>
            );

            return (
              <li key={item.label}>
                {item.href ? (
                  <a
                    href={item.href}
                    aria-current={item.current ? 'page' : undefined}
                    onClick={onNavigate}
                    className={
                      item.current
                        ? 'flex items-center gap-3 rounded-xl bg-white/[0.11] px-3 py-2.5 text-sm font-medium text-white shadow-inner shadow-white/[0.04]'
                        : 'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-white/75 transition hover:bg-white/[0.07] hover:text-white focus-visible:text-white'
                    }
                  >
                    {content}
                  </a>
                ) : (
                  <button
                    type="button"
                    disabled
                    className="flex w-full cursor-not-allowed items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium text-white/60"
                  >
                    {content}
                  </button>
                )}
              </li>
            );
          })}
        </ul>

        <p className="mt-8 mb-2 px-3 text-[10px] font-semibold tracking-[0.18em] text-white/70 uppercase">
          Manage
        </p>
        <button
          type="button"
          disabled
          className="flex w-full cursor-not-allowed items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium text-white/60"
        >
          <Settings
            className="size-[18px]"
            strokeWidth={1.8}
            aria-hidden="true"
          />
          Settings
          <span className="ml-auto rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold text-white/75">
            Soon
          </span>
        </button>
      </nav>

      <ApiFoundationStatus status={foundationStatus} />
    </div>
  );
}

interface TopBarProps {
  readonly isNavigationOpen: boolean;
  readonly menuButtonRef: RefObject<HTMLButtonElement | null>;
  readonly onOpenNavigation: () => void;
}

function TopBar({
  isNavigationOpen,
  menuButtonRef,
  onOpenNavigation,
}: TopBarProps) {
  return (
    <header className="sticky top-0 z-30 flex h-[76px] items-center border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur md:px-7 lg:px-9">
      <button
        ref={menuButtonRef}
        type="button"
        onClick={onOpenNavigation}
        className="mr-3 grid size-10 place-items-center rounded-xl text-slate-700 hover:bg-slate-100 lg:hidden"
        aria-label="Open navigation"
        aria-controls="mobile-navigation-dialog"
        aria-expanded={isNavigationOpen}
      >
        <Menu className="size-5" aria-hidden="true" />
      </button>

      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-slate-600">
          Thursday, 23 July
        </p>
        <h1 className="truncate text-[15px] font-semibold text-slate-800">
          Personal workspace
        </h1>
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm sm:inline-flex">
          July 2026
        </span>
        <div
          className="flex items-center gap-2"
          aria-label="Demo account: Mohd Salik"
        >
          <span className="bg-ink-800 grid size-8 place-items-center rounded-lg text-xs font-semibold text-white">
            MS
          </span>
          <span className="hidden text-left xl:block">
            <span className="block text-xs font-semibold text-slate-700">
              Mohd Salik
            </span>
            <span className="block text-[10px] font-medium text-slate-600">
              Demo account
            </span>
          </span>
        </div>
      </div>
    </header>
  );
}

export function AppShell({ children }: PropsWithChildren) {
  const [isNavigationOpen, setIsNavigationOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const foundationStatus = useFoundationStatus();

  const getDialogFocusableElements = () => {
    const dialog = dialogRef.current;
    return dialog
      ? Array.from(dialog.querySelectorAll<HTMLElement>('*')).filter(
          (element) =>
            element.matches(
              'a[href], button:not(:disabled):not([tabindex="-1"])',
            ),
        )
      : [];
  };

  useEffect(() => {
    if (!isNavigationOpen) {
      return;
    }

    const menuButton = menuButtonRef.current;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setIsNavigationOpen(false);
      }
    };

    const keepFocusInDialog = (event: FocusEvent) => {
      if (dialog && !dialog.contains(event.target as Node)) {
        closeButtonRef.current?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('focusin', keepFocusInDialog);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('focusin', keepFocusInDialog);
      document.body.style.overflow = previousOverflow;
      menuButton?.focus();
    };
  }, [isNavigationOpen]);

  return (
    <div className="min-h-screen bg-mist-50 text-slate-900">
      <div
        data-testid="app-background"
        inert={isNavigationOpen}
        aria-hidden={isNavigationOpen}
      >
        <a
          href="#main-content"
          className="text-ink-900 fixed top-3 left-3 z-[70] -translate-y-20 rounded-lg bg-white px-4 py-2 text-sm font-semibold shadow-lg transition focus:translate-y-0"
        >
          Skip to content
        </a>

        <aside className="fixed inset-y-0 left-0 z-40 hidden w-[244px] lg:block">
          <Sidebar foundationStatus={foundationStatus} />
        </aside>

        <div className="lg:pl-[244px]">
          <TopBar
            isNavigationOpen={isNavigationOpen}
            menuButtonRef={menuButtonRef}
            onOpenNavigation={() => setIsNavigationOpen(true)}
          />
          <main id="main-content">{children}</main>
        </div>
      </div>

      {isNavigationOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            tabIndex={-1}
            className="bg-ink-950/60 absolute inset-0 backdrop-blur-[2px]"
            aria-label="Close navigation"
            onClick={() => setIsNavigationOpen(false)}
          />
          <aside
            ref={dialogRef}
            id="mobile-navigation-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation menu"
            className="relative h-full w-[min(86vw,290px)] shadow-2xl"
          >
            <span
              tabIndex={0}
              className="sr-only"
              onFocus={() => getDialogFocusableElements().at(-1)?.focus()}
            >
              Wrap focus to the end of the navigation menu
            </span>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={() => setIsNavigationOpen(false)}
              className="absolute top-4 right-3 z-10 grid size-9 place-items-center rounded-lg text-white/80 hover:bg-white/10 hover:text-white"
              aria-label="Close navigation panel"
            >
              <X className="size-5" aria-hidden="true" />
            </button>
            <Sidebar
              foundationStatus={foundationStatus}
              onNavigate={() => setIsNavigationOpen(false)}
            />
            <span
              tabIndex={0}
              className="sr-only"
              onFocus={() => getDialogFocusableElements()[0]?.focus()}
            >
              Wrap focus to the start of the navigation menu
            </span>
          </aside>
        </div>
      )}
    </div>
  );
}
