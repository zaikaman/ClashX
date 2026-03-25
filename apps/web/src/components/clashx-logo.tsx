export function ClashXLogo({ className }: { className?: string }) {
  return (
    <svg 
      viewBox="0 0 32 32" 
      fill="none" 
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path 
        d="M4 4H12L28 28H20L4 4Z" 
        fill="currentColor" 
      />
      <path 
        d="M28 4H20L4 28H12L28 4Z" 
        fill="#dce85d" 
        style={{ mixBlendMode: 'screen' }}
      />
      <circle cx="16" cy="16" r="3" fill="#090a0a" />
    </svg>
  );
}
