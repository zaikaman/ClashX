import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#fefce8',
          100: '#fef9c3',
          200: '#fef08a',
          300: '#fde047',
          400: '#facc15',
          500: '#dce85d',
          600: '#c5d048',
          700: '#a8b63d',
          800: '#6b7229',
          900: '#4a5017',
        },
        dark: {
          50: '#fafafa',
          100: '#f4f4f5',
          200: '#e4e4e7',
          300: '#d4d4d8',
          400: '#a1a1aa',
          500: '#71717a',
          600: '#52525b',
          700: '#3f3f46',
          800: '#27272a',
          900: '#18181b',
          950: '#0a0a0f',
        },
        neutral: {
          50: '#fcfcfc',
          100: '#f4f4f5',
          200: '#e4e4e7',
          300: '#a1a1aa',
          400: '#868e95',
          500: '#71717a',
          600: '#52525b',
          700: '#3f3f46',
          800: '#27272a',
          900: '#18181b',
        },
        success: {
          400: '#74b97f',
          500: '#74b97f',
          600: '#5da568',
        },
        error: {
          400: '#e06c6e',
          500: '#e06c6e',
          600: '#c85a5c',
        },
        warning: {
          400: '#dca204',
          500: '#dca204',
          600: '#c29003',
        },
        info: {
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
        },
      },
      backgroundColor: {
        'app': '#090a0a',
        'card': '#16181a',
        'secondary': '#161a1d',
        'tertiary': '#1a1e21',
        'hover': '#1e2225',
        'input': '#292e32',
      },
      borderColor: {
        'default': 'rgba(255, 255, 255, 0.06)',
        'hover': 'rgba(220, 232, 93, 0.3)',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['Inconsolata', 'Courier New', 'monospace'],
      },
      fontSize: {
        'xs': ['0.6875rem', { lineHeight: '1rem' }],
        'sm': ['0.8125rem', { lineHeight: '1.25rem' }],
        'base': ['0.875rem', { lineHeight: '1.5rem' }],
        'lg': ['0.9375rem', { lineHeight: '1.75rem' }],
        'xl': ['1rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.25rem', { lineHeight: '2rem' }],
        '3xl': ['1.5rem', { lineHeight: '2.25rem' }],
        '4xl': ['2rem', { lineHeight: '2.5rem' }],
        '5xl': ['2.5rem', { lineHeight: '3rem' }],
        '6xl': ['3.75rem', { lineHeight: '1' }],
        '7xl': ['4.5rem', { lineHeight: '1' }],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'shimmer': 'shimmer 2s linear infinite',
        'spin-slow': 'spin 4s linear infinite',
        'shimmer-rotate': 'shimmerRotate 4s linear infinite',
        'marquee-ltr': 'marqueeLtr 30s linear infinite',
        'marquee-rtl': 'marqueeRtl 30s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideIn: {
          '0%': { opacity: '0', transform: 'translateX(-10px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        shimmerRotate: {
          '0%': { transform: 'translate(-50%, -50%) rotate(0deg)' },
          '100%': { transform: 'translate(-50%, -50%) rotate(360deg)' },
        },
        marqueeLtr: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
        marqueeRtl: {
          '0%': { transform: 'translateX(-50%)' },
          '100%': { transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
