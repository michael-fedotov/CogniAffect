/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#4F46E5',
        'primary-dark': '#4338CA',
        success: '#10B981',
        warning: '#F59E0B',
        surface: '#FFFFFF',
        background: '#F8FAFC',
        'text-primary': '#0F172A',
        'text-secondary': '#475569',
      },
    },
  },
  plugins: [],
};
