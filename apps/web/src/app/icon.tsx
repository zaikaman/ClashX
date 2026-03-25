import { ImageResponse } from 'next/og';

export const runtime = 'edge';
export const size = { width: 32, height: 32 };
export const contentType = 'image/png';

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#090a0a',
          borderRadius: '8px',
        }}
      >
        <svg
          viewBox="0 0 32 32"
          width="24"
          height="24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M4 4H12L28 28H20L4 4Z"
            fill="#ffffff"
          />
          <path
            d="M28 4H20L4 28H12L28 4Z"
            fill="#dce85d"
          />
          <circle cx="16" cy="16" r="3" fill="#090a0a" />
        </svg>
      </div>
    ),
    { ...size }
  );
}
