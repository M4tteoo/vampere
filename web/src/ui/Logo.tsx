/** Marchio provvisorio «vampére» (verrà sostituito dal logo vero): una goccia-vampiro verde con due canini. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden>
        <path d="M16 2c5 6 11 10.5 11 17a11 11 0 01-22 0C5 12.5 11 8 16 2z" fill="#1f7a57" />
        <path d="M11.5 20l1.6 4.2 1.6-4.2zM17.3 20l1.6 4.2 1.6-4.2z" fill="#fff" />
      </svg>
      <span className="text-[20px] font-semibold tracking-[-0.4px] text-primary">vampére</span>
    </span>
  )
}
