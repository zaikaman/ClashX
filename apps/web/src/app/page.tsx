"use client";

import { motion, AnimatePresence, useInView } from 'framer-motion';
import Link from 'next/link';
import Script from 'next/script';
import {
  ArrowRight, Shield, Zap, TrendingUp, Box, Users,
  Activity, ShieldCheck, Layers, Menu, X,
  Github, Twitter, Send, FileText, BookOpen
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { ClashXLogo } from '@/components/clashx-logo';
import { useTransition } from '@/components/providers/transition-provider';
import { getPreferredLaunchPath } from '@/lib/onboarding-state';

const AnimatedCounter = ({ value, suffix = '' }: { value: string; suffix?: string }) => {
  const ref = useRef<HTMLDivElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-50px' });
  const [display, setDisplay] = useState('0');

  const numericPart = value.replace(/[^0-9.]/g, '');
  const prefix = value.replace(/[0-9.+%KMB]/g, '');

  useEffect(() => {
    if (!isInView) return;
    const target = parseFloat(numericPart);
    if (isNaN(target)) { setDisplay(value); return; }

    const duration = 1200;
    const startTime = performance.now();
    const easeOutQuart = (t: number) => 1 - Math.pow(1 - t, 4);

    const step = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = easeOutQuart(progress);
      const current = eased * target;

      if (target >= 1) {
        setDisplay(Math.round(current).toString());
      } else {
        setDisplay(current.toFixed(1));
      }

      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [isInView, numericPart, value]);

  return <div ref={ref}>{prefix}{display}{suffix}</div>;
};

const LandingHeader = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { triggerTransition } = useTransition();

  const handleStartBuilding = () => {
    triggerTransition(getPreferredLaunchPath());
  };

  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileMenuOpen]);

  const navItems = [
    { href: '#features', label: 'Features' },
    { href: '#how-it-works', label: 'How It Works' },
    { href: '/bots', label: 'Bots' },
    { href: '/docs', label: 'Docs' },
  ];

  const handleNavClick = (href: string, e: React.MouseEvent) => {
    if (href.startsWith('#')) {
      e.preventDefault();
      const element = document.getElementById(href.substring(1));
      if (element) {
        element.scrollIntoView({ behavior: 'smooth' });
      }
    }
    setMobileMenuOpen(false);
  };

  return (
    <motion.header
      initial={{ y: -10, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="fixed top-0 left-0 right-0 z-50 pt-6 px-6"
    >
      <div
        className="max-w-7xl mx-auto rounded-full px-6 py-3"
        style={{
          background: 'linear-gradient(180deg, rgba(9,10,10,0.75), rgba(9,10,10,0.45)) padding-box, linear-gradient(120deg, rgba(220,232,93,0.25), rgba(255,255,255,0.08)) border-box',
          border: '1px solid transparent',
          backdropFilter: 'blur(16px) saturate(120%)',
          WebkitBackdropFilter: 'blur(16px) saturate(120%)',
          boxShadow: '0 10px 30px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.04)'
        }}
      >
        <div className="flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 group">
            <ClashXLogo className="w-6 h-6 text-white group-hover:scale-105 transition-transform duration-300" />
            <div className="flex items-baseline font-black tracking-tighter text-lg uppercase">
              <span className="text-white">Clash</span>
              <span className="text-[#dce85d] ml-[1px]">X</span>
            </div>
          </Link>

          <nav className="hidden md:flex items-center gap-1 text-sm font-medium text-white/60">
            {navItems.map((item) => {
              if (item.href.startsWith('/')) {
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="hover:text-white transition-colors duration-300 px-4 py-2 rounded-full hover:bg-white/5"
                  >
                    {item.label}
                  </Link>
                );
              }
              return (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={(e) => handleNavClick(item.href, e)}
                  className="hover:text-white transition-colors duration-300 px-4 py-2 rounded-full hover:bg-white/5"
                >
                  {item.label}
                </a>
              );
            })}
          </nav>

          <div className="hidden md:flex items-center gap-2">
            <button onClick={handleStartBuilding} className="group relative inline-flex items-center justify-center h-[38px] px-5 gap-2 text-sm font-semibold text-[#090a0a] bg-[#dce85d] rounded-full overflow-hidden transition-all duration-300 ease-out hover:scale-105 hover:bg-[#e4ef6e] focus:outline-none focus:ring-2 focus:ring-[#dce85d] focus:ring-offset-2 focus:ring-offset-[#090a0a]">
              <span className="relative z-10 flex items-center gap-1.5 whitespace-nowrap">
                Start Building
                <ArrowRight className="w-3.5 h-3.5 transition-transform duration-300 group-hover:translate-x-0.5" />
              </span>
              <div className="absolute inset-0 z-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out rounded-full shadow-[inset_0_1px_1px_rgba(255,255,255,0.4)]"></div>
            </button>
          </div>

          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 text-white hover:text-white/80 transition-colors rounded-full hover:bg-white/10"
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {mobileMenuOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 bg-black/80 backdrop-blur-md z-40 md:hidden"
              onClick={() => setMobileMenuOpen(false)}
            />

            <motion.div
              initial={{ opacity: 0, x: '100%' }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="fixed top-0 right-0 bottom-0 w-full max-w-sm bg-[#090a0a] z-50 md:hidden overflow-y-auto"
              style={{
                borderLeft: '1px solid rgba(255,255,255,0.1)',
              }}
            >
              <div className="flex items-center justify-between p-6 border-b border-white/10">
                <span className="text-white text-xl font-semibold">ClashX</span>
                <button
                  onClick={() => setMobileMenuOpen(false)}
                  className="p-2.5 text-white/80 hover:text-white transition-colors rounded-full hover:bg-white/10"
                >
                  <X size={24} />
                </button>
              </div>

              <div className="flex flex-col p-6 space-y-8">
                <nav className="flex flex-col gap-2">
                  <div className="text-xs font-semibold text-white/40 uppercase tracking-wider mb-3 px-2">Menu</div>
                  {navItems.map((item, index) => {
                    const content = (
                      <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="relative"
                      >
                        <div className="px-5 py-4 rounded-xl text-lg font-medium transition-all duration-200 text-white hover:bg-white/5 active:bg-white/10 flex items-center justify-between group">
                          <span>{item.label}</span>
                          <svg className="w-5 h-5 text-white/40 group-hover:text-white/60 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </div>
                      </motion.div>
                    );

                    if (item.href.startsWith('/')) {
                      return <Link key={item.href} href={item.href} onClick={() => setMobileMenuOpen(false)}>{content}</Link>;
                    }
                    return <a key={item.href} href={item.href} onClick={(e) => handleNavClick(item.href, e)}>{content}</a>;
                  })}
                </nav>

                <div className="border-t border-white/10" />

                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 }}
                  className="space-y-4"
                >
                  <div className="text-xs font-semibold text-white/40 uppercase tracking-wider px-2">Build</div>
                  <button onClick={handleStartBuilding} className="w-full group isolate inline-flex justify-center cursor-pointer overflow-hidden transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_0_40px_8px_rgba(220,232,93,0.35)] rounded-full relative shadow-[0_8px_40px_rgba(220,232,93,0.25)] h-12">
                    <div className="absolute inset-0">
                      <div className="absolute inset-[-200%] w-[400%] h-[400%] animate-[rotate-gradient_4s_linear_infinite]">
                        <div className="absolute inset-0" style={{ background: 'conic-gradient(from 225deg, transparent 0, rgba(255,255,255,0.6) 90deg, transparent 90deg)' }}></div>
                      </div>
                    </div>
                    <div className="absolute rounded-full backdrop-blur" style={{ inset: '1px', background: 'rgba(220, 232, 93, 0.1)' }}></div>
                    <div className="z-10 flex gap-2 overflow-hidden text-base font-medium text-white w-full px-5 relative items-center justify-center rounded-full">
                      <div className="absolute inset-[1px] bg-[rgba(10,11,20,0.8)] rounded-full backdrop-blur-[8px]"></div>
                      <span className="whitespace-nowrap relative z-10 font-sans">Start Building</span>
                      <span className="inline-flex items-center justify-center z-10 bg-white/10 w-6 h-6 rounded-full relative"><ArrowRight className="w-4 h-4" /></span>
                    </div>
                  </button>
                </motion.div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </motion.header>
  );
};

const Footer = () => {
  return (
    <footer className="border-t border-default bg-secondary mt-auto">
      <div className="container mx-auto px-4 max-w-7xl">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-4">
            <span className="text-xs text-neutral-500">Powered by</span>
            <a href="https://pacifica.network" target="_blank" rel="noopener noreferrer" className="text-xs text-neutral-400 hover:text-neutral-50 transition-colors font-medium">
              Pacifica
            </a>
          </div>

          <div className="hidden md:flex items-center gap-3">
            <a href="https://twitter.com" target="_blank" rel="noopener noreferrer" className="p-1.5 text-neutral-400 hover:text-neutral-50 transition-colors">
              <Twitter size={16} />
            </a>
            <a href="https://discord.com" target="_blank" rel="noopener noreferrer" className="p-1.5 text-neutral-400 hover:text-neutral-50 transition-colors">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M13.545 2.907a13.227 13.227 0 0 0-3.257-1.011.05.05 0 0 0-.052.025c-.141.25-.297.577-.406.833a12.19 12.19 0 0 0-3.658 0 8.258 8.258 0 0 0-.412-.833.051.051 0 0 0-.052-.025c-1.125.194-2.22.534-3.257 1.011a.041.041 0 0 0-.021.018C.356 6.024-.213 9.047.066 12.032c.001.014.01.028.021.037a13.276 13.276 0 0 0 3.995 2.02.05.05 0 0 0 .056-.019c.308-.42.582-.863.818-1.329a.05.05 0 0 0-.01-.059.051.051 0 0 0-.018-.011 8.875 8.875 0 0 1-1.248-.595.05.05 0 0 1-.02-.066.051.051 0 0 1 .015-.019c.084-.063.168-.129.248-.195a.05.05 0 0 1 .051-.007c2.619 1.196 5.454 1.196 8.041 0a.052.052 0 0 1 .053.007c.08.066.164.132.248.195a.051.051 0 0 1-.004.085 8.254 8.254 0 0 1-1.249.594.05.05 0 0 0-.03.03.052.052 0 0 0 .003.041c.24.465.515.909.817 1.329a.05.05 0 0 0 .056.019 13.235 13.235 0 0 0 4.001-2.02.049.049 0 0 0 .021-.037c.334-3.451-.559-6.449-2.366-9.106a.034.034 0 0 0-.02-.019Zm-8.198 7.307c-.789 0-1.438-.724-1.438-1.612 0-.889.637-1.613 1.438-1.613.807 0 1.45.73 1.438 1.613 0 .888-.637 1.612-1.438 1.612Zm5.316 0c-.788 0-1.438-.724-1.438-1.612 0-.889.637-1.613 1.438-1.613.807 0 1.451.73 1.438 1.613 0 .888-.631 1.612-1.438 1.612Z" />
              </svg>
            </a>
            <a href="https://github.com" target="_blank" rel="noopener noreferrer" className="p-1.5 text-neutral-400 hover:text-neutral-50 transition-colors">
              <Github size={16} />
            </a>
            <a href="https://t.me" target="_blank" rel="noopener noreferrer" className="p-1.5 text-neutral-400 hover:text-neutral-50 transition-colors">
              <Send size={16} />
            </a>
            <span className="w-px h-4 bg-default mx-1" />
            <Link href="/docs" className="p-1.5 text-neutral-400 hover:text-neutral-50 transition-colors">
              <BookOpen size={16} />
            </Link>
            <Link href="/terms" className="p-1.5 text-neutral-400 hover:text-neutral-50 transition-colors">
              <FileText size={16} />
            </Link>
          </div>

          <div className="text-xs text-neutral-500">v1.0.0</div>
        </div>
      </div>
    </footer>
  );
};

const Home = () => {
  const { triggerTransition } = useTransition();
  const [isMobile, setIsMobile] = useState(false);

  const unicornInitializedRef = useRef(false);

  const handleStartBuilding = () => {
    triggerTransition(getPreferredLaunchPath());
  };

  const initUnicorn = () => {
    if (typeof window === 'undefined' || unicornInitializedRef.current) {
      return;
    }

    const UnicornStudio = (window as typeof window & { UnicornStudio?: { init: () => void } }).UnicornStudio;
    if (!UnicornStudio) {
      return;
    }

    try {
      UnicornStudio.init();
      unicornInitializedRef.current = true;
    } catch (error) {
      console.error('Error initializing UnicornStudio:', error);
    }
  };

  useEffect(() => {
    initUnicorn();
  }, []);


  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);



  const stats = useMemo(() => [
    { label: 'Total Trading Volume', value: '$76M', change: '+12.5%', icon: TrendingUp },
    { label: 'Active Bots', value: '600+', change: '+23.1%', icon: Box },
    { label: 'Total Users', value: '80K', change: '+8.3%', icon: Users },
    { label: 'Avg Win Rate', value: '68%', change: '+2.1%', icon: Zap },
  ], []);

  const platformFeatures = useMemo(() => [
    { icon: Activity, tag: 'Observability', title: 'Runtime logs' },
    { icon: ShieldCheck, tag: 'Custody', title: 'Delegated wallets' },
    { icon: Layers, tag: 'Execution', title: 'Advanced controls' },
    { icon: Users, tag: 'Community', title: 'Bot cloning' },
  ], []);

  const trustedBy = useMemo(() => [
    'Soroban Labs', 'Pacifica Foundation', 'DeFi Alliance',
    'Meridian Protocol', 'Anchor Platform', 'TradingSpace'
  ], []);

  const testimonials = useMemo(() => [
    {
      name: 'Alex Kim',
      handle: '@alexk_defi',
      initial: 'AK',
      color: 'from-[#dce85d] to-[#a8c93a]',
      text: 'ClashX made tracking your performance so simple. You can easily deploy a bot to mirror other users.',
    },
    {
      name: 'Sarah Martinez',
      handle: '@sarahm_tradings',
      initial: 'SM',
      color: 'from-[#74b97f] to-[#5a9268]',
      text: 'Cloning a top marketplace bot transformed my trading. The copy limits keep me perfectly safe.',
    },
    {
      name: 'James Park',
      handle: '@jpark_stellar',
      initial: 'JP',
      color: 'from-[#a8c93a] to-[#8ba631]',
      text: 'Delegated execution through my Pacifica wallet gives me complete peace of mind. Exactly how it should work.',
    },
    {
      name: 'Lisa Chen',
      handle: '@lisac_crypto',
      initial: 'LC',
      color: 'from-[#dce85d] to-[#c8d750]',
      text: 'Monitoring my bot execution, risk limits, and live performance across dozens of markets is seamless.',
    },
    {
      name: 'Marcus Rivera',
      handle: '@mrivera_dev',
      initial: 'MR',
      color: 'from-[#a8c93a] to-[#8ba631]',
      text: 'The visual rules engine is incredibly powerful. Setting conditions for custom bot strategies is intuitive.',
    },
    {
      name: 'Emma Nguyen',
      handle: '@emman_blockchain',
      initial: 'EN',
      color: 'from-[#74b97f] to-[#5a9268]',
      text: 'Real-time monitoring and automated rebalancing keep my bots optimized. Best Pacifica DeFi tool I\'ve used.',
    },
  ], []);

  const steps = useMemo(() => [
    {
      step: '01',
      title: 'Connect Wallet',
      description: 'Connect your Pacifica wallet and authorize execution',
    },
    {
      step: '02',
      title: 'Build Strategy',
      description: 'Use visual blocks to design your trading bot',
    },
    {
      step: '03',
      title: 'Deploy & Earn',
      description: 'Deploy your bot or copy a winner and trade automatically',
    },
  ], []);

  const duplicatedCommunity = useMemo(() => {
    const row1 = testimonials.slice(0, 3);
    const row2 = testimonials.slice(3);
    return { row1, row2 };
  }, [testimonials]);

  return (
    <div className="min-h-screen bg-app flex flex-col">
      <Script src="/unicornStudio.umd.js" strategy="afterInteractive" onLoad={initUnicorn} />
      <LandingHeader />

      <main className="flex-grow">
        {/* Hero Section */}
        <section className="relative overflow-hidden min-h-[85vh] flex items-center pt-32 pb-24 md:pt-48 md:pb-32 bg-app">
          {/* UnicornStudio Animated Background with loading fallback */}
          <div
            data-us-project="4gq2Yrv2p0bIa0hdLPQx"
            className="absolute inset-0 w-full h-full"
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              zIndex: 0,
              background: 'radial-gradient(circle at 50% 50%, rgba(220, 232, 93, 0.1) 0%, rgba(9, 10, 10, 0) 50%)',
            }}
          />


          <div className="container mx-auto px-4 max-w-6xl relative z-10">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="text-center"
            >
              <motion.h1
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0, duration: 0.3 }}
                className="text-5xl md:text-7xl font-bold mb-4 text-white tracking-tight leading-[0.95]"
              >
                Social Bot Trading on{' '}
                <span className="text-[#dce85d]">Pacifica</span>
              </motion.h1>

              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.1, duration: 0.3 }}
                className="text-lg md:text-xl text-[#a1a1aa] mb-8 max-w-2xl mx-auto"
              >
                Create, deploy, and copy high-performing trading bots.
                No manual trading required. Maximum control. Optimal returns.
              </motion.p>

              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.3 }}
                className="flex flex-col sm:flex-row gap-3 justify-center mb-16"
              >
                <div className="w-full sm:w-auto max-w-[360px] mx-auto">
                  <button onClick={handleStartBuilding} className="group isolate inline-flex cursor-pointer overflow-hidden transition-all duration-300 hover:scale-105 hover:shadow-[0_0_40px_8px_rgba(220,232,93,0.35)] rounded-full relative shadow-[0_8px_40px_rgba(220,232,93,0.25)]">
                    <div className="absolute inset-0">
                      <div className="absolute inset-[-200%] w-[400%] h-[400%] animate-[rotate-gradient_4s_linear_infinite]">
                        <div className="absolute inset-0" style={{ background: 'conic-gradient(from 225deg, transparent 0, rgba(255,255,255,0.6) 90deg, transparent 90deg)' }}></div>
                      </div>
                    </div>
                    <div className="absolute rounded-full backdrop-blur" style={{ inset: '1px', background: 'rgba(220, 232, 93, 0.1)' }}></div>
                    <div className="z-10 flex gap-3 overflow-hidden text-base font-medium text-white w-full pt-3 pr-5 pb-3 pl-5 relative items-center rounded-full">
                      <div className="absolute inset-[1px] bg-[rgba(10,11,20,0.8)] rounded-full backdrop-blur-[8px]"></div>
                      <span className="whitespace-nowrap relative z-10 font-sans">Start Building</span>
                      <span className="inline-flex items-center justify-center z-10 bg-white/10 w-7 h-7 rounded-full relative"><ArrowRight className="w-4 h-4" /></span>
                    </div>
                  </button>
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, duration: 0.3 }}
                className="grid grid-cols-2 md:grid-cols-4 gap-3"
              >
                {stats.map((stat, idx) => {
                  const Icon = stat.icon;
                  const numericValue = stat.value.replace(/[^0-9.]/g, '');
                  const prefix = stat.value.replace(/[0-9.]/g, '').replace(/[KMB+%]/g, '');
                  const suffix = stat.value.replace(/[^KMB+%]/g, '');
                  return (
                    <motion.div
                      key={stat.label}
                      initial={{ opacity: 0, y: 15 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.35 + idx * 0.08, duration: 0.4, ease: [0.25, 1, 0.5, 1] }}
                      className="p-4 text-center bg-card rounded-xl border border-white/[0.06] hover:border-[#dce85d]/30 transition-colors"
                    >
                      <div className="flex items-center justify-center gap-2 mb-2">
                        <Icon className="w-4 h-4 text-[#dce85d]" />
                        <div className="text-2xl font-bold text-neutral-50">
                          <AnimatedCounter value={numericValue} suffix={suffix.startsWith('%') ? '%' : suffix} />
                        </div>
                        {prefix && <span className="text-2xl font-bold text-neutral-50">{prefix}</span>}
                      </div>
                      <div className="text-xs text-neutral-400 mb-1">{stat.label}</div>
                      <div className="text-xs text-[#74b97f] font-medium">{stat.change}</div>
                    </motion.div>
                  );
                })}
              </motion.div>
            </motion.div>
          </div>
        </section>

        {/* Trusted By Section */}
        <section className="py-12 relative">
          <div className="max-w-7xl mx-auto px-4">
            <div className="text-center mb-8">
              <p className="uppercase text-xs font-medium text-[#a1a1aa] tracking-wide">Trusted by teams at</p>
            </div>
            <div
              className="overflow-hidden relative"
              style={{ maskImage: 'linear-gradient(to right, transparent, black 15%, black 85%, transparent)', WebkitMaskImage: 'linear-gradient(to right, transparent, black 15%, black 85%, transparent)' }}
            >
              <div className="flex gap-16 py-2 items-center animate-[marqueeLtr_30s_linear_infinite]">
                <div className="flex gap-16 shrink-0 items-center">
                  {trustedBy.map((company, idx) => (
                    <span key={idx} className={`text-lg ${idx % 2 === 0 ? 'font-normal' : 'font-semibold'} tracking-tighter text-[#a1a1aa] hover:text-white transition whitespace-nowrap`}>
                      {company}
                    </span>
                  ))}
                </div>
                <div className="flex gap-16 shrink-0 items-center">
                  {trustedBy.map((company, idx) => (
                    <span key={`dup-${idx}`} className={`text-lg ${idx % 2 === 0 ? 'font-normal' : 'font-semibold'} tracking-tighter text-[#a1a1aa] hover:text-white transition whitespace-nowrap`}>
                      {company}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Engine Section — live signal pipeline */}
        <section id="features" className="py-24 md:py-32 relative bg-[#090a0a] overflow-hidden">
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/[0.08] to-transparent" />
            <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/[0.08] to-transparent" />
          </div>

          <div className="max-w-7xl mx-auto px-4 sm:px-8 relative z-10">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-start">

              {/* Left — editorial intro */}
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6 }}
                className="lg:sticky lg:top-32"
              >
                <span className="inline-block text-[10px] font-mono tracking-[0.2em] uppercase text-white/40 mb-6">How it works under the hood</span>
                <h2 className="text-4xl md:text-5xl lg:text-6xl font-bold text-white tracking-tight leading-[1.05] mb-6">
                  The engine behind<br />
                  every <span className="text-[#dce85d]">trade</span>
                </h2>
                <p className="text-[#868e95] text-lg leading-relaxed max-w-md mb-10">
                  Your bots don&apos;t sleep. Every tick, ClashX evaluates live market data against your rules, validates risk limits, and executes through Pacifica&apos;s on-chain order book — all in sub-second cycles.
                </p>

                {/* Pipeline steps */}
                <div className="space-y-0">
                  {[
                    { num: '01', label: 'Signal Detection', desc: 'Price feeds, candlesticks, and indicator streams ingested in real-time' },
                    { num: '02', label: 'Rule Evaluation', desc: 'Your condition graph is walked node-by-node against current state' },
                    { num: '03', label: 'Risk Gate', desc: 'Position size, leverage, and drawdown limits validated before submission' },
                    { num: '04', label: 'Execution', desc: 'Market or limit order placed via delegated wallet on Pacifica' },
                  ].map((step, idx) => (
                    <motion.div
                      key={step.num}
                      initial={{ opacity: 0, x: -20 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.4, delay: idx * 0.1 }}
                      className="group flex items-start gap-5 py-5 relative"
                    >
                      {idx < 3 && (
                        <div className="absolute left-[15px] top-[52px] bottom-0 w-px bg-gradient-to-b from-white/[0.08] to-transparent" />
                      )}
                      <div className="flex-shrink-0 w-[30px] h-[30px] rounded-lg bg-white/[0.03] border border-white/[0.08] flex items-center justify-center relative z-10">
                        <span className="text-[10px] font-mono text-white/50 group-hover:text-[#dce85d] transition-colors">{step.num}</span>
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-white mb-0.5">{step.label}</div>
                        <div className="text-xs text-white/40 leading-relaxed">{step.desc}</div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </motion.div>

              {/* Right — simulated live signal feed */}
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.6, delay: 0.15 }}
                className="relative"
              >
                {/* Terminal-style feed container */}
                <div className="bg-[#0c0d0e] rounded-2xl border border-white/[0.06] overflow-hidden">
                  {/* Terminal header */}
                  <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.06]">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-[#74b97f] shadow-[0_0_6px_rgba(116,185,127,0.5)]" />
                      <span className="text-[10px] font-mono text-white/40 tracking-wide">LIVE EXECUTION FEED</span>
                    </div>
                    <span className="text-[10px] font-mono text-white/20">bot_runtime_worker</span>
                  </div>

                  {/* Feed entries */}
                  <div className="divide-y divide-white/[0.04]">
                    {/* Entry 1 — Signal detected */}
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.3, ease: [0.25, 1, 0.5, 1] }}
                      className="px-5 py-4"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#dce85d]" />
                        <span className="text-[10px] font-mono text-white/30">00:00:01.204</span>
                        <span className="text-[10px] font-mono text-[#dce85d]/70 bg-[#dce85d]/[0.06] px-1.5 py-0.5 rounded">SIGNAL</span>
                      </div>
                      <div className="ml-[18px] space-y-1">
                        <div className="text-xs text-white/70">RSI crossed below <span className="text-[#dce85d] font-mono">30</span> on SOL-PERP (15m)</div>
                        <div className="text-[10px] font-mono text-white/25">rsi_value=28.4 · threshold=30.0 · direction=below</div>
                      </div>
                    </motion.div>

                    {/* Entry 2 — Rule evaluation */}
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.5, ease: [0.25, 1, 0.5, 1] }}
                      className="px-5 py-4"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#a8c93a]" />
                        <span className="text-[10px] font-mono text-white/30">00:00:01.207</span>
                        <span className="text-[10px] font-mono text-[#a8c93a]/70 bg-[#a8c93a]/[0.06] px-1.5 py-0.5 rounded">EVAL</span>
                      </div>
                      <div className="ml-[18px] space-y-1">
                        <div className="text-xs text-white/70">Condition graph evaluated — <span className="text-white font-medium">2 of 3</span> nodes triggered</div>
                        <div className="flex items-center gap-3 mt-2">
                          <div className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-[#dce85d]/20 flex items-center justify-center"><div className="w-1 h-1 rounded-full bg-[#dce85d]" /></div>
                            <span className="text-[10px] font-mono text-white/30">rsi_below</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-[#dce85d]/20 flex items-center justify-center"><div className="w-1 h-1 rounded-full bg-[#dce85d]" /></div>
                            <span className="text-[10px] font-mono text-white/30">price_above_sma</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <div className="w-3 h-3 rounded bg-white/[0.04] flex items-center justify-center"><div className="w-1 h-1 rounded-full bg-white/20" /></div>
                            <span className="text-[10px] font-mono text-white/20">volume_spike</span>
                          </div>
                        </div>
                      </div>
                    </motion.div>

                    {/* Entry 3 — Risk check */}
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.7, ease: [0.25, 1, 0.5, 1] }}
                      className="px-5 py-4"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#74b97f]" />
                        <span className="text-[10px] font-mono text-white/30">00:00:01.209</span>
                        <span className="text-[10px] font-mono text-[#74b97f]/70 bg-[#74b97f]/[0.06] px-1.5 py-0.5 rounded">RISK</span>
                      </div>
                      <div className="ml-[18px]">
                        <div className="text-xs text-white/70">Risk gate <span className="text-[#74b97f] font-medium">passed</span></div>
                        <div className="grid grid-cols-3 gap-4 mt-2">
                          <div>
                            <div className="text-[10px] font-mono text-white/20 mb-0.5">leverage</div>
                            <div className="text-xs font-mono text-white/60">3x <span className="text-white/20">/ 10x</span></div>
                          </div>
                          <div>
                            <div className="text-[10px] font-mono text-white/20 mb-0.5">drawdown</div>
                            <div className="text-xs font-mono text-white/60">2.1% <span className="text-white/20">/ 8%</span></div>
                          </div>
                          <div>
                            <div className="text-[10px] font-mono text-white/20 mb-0.5">size</div>
                            <div className="text-xs font-mono text-white/60">$420</div>
                          </div>
                        </div>
                      </div>
                    </motion.div>

                    {/* Entry 4 — Order placed */}
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.9, ease: [0.25, 1, 0.5, 1] }}
                      className="px-5 py-4 bg-[#dce85d]/[0.02]"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#dce85d] shadow-[0_0_6px_rgba(220,232,93,0.4)]" />
                        <span className="text-[10px] font-mono text-white/30">00:00:01.215</span>
                        <span className="text-[10px] font-mono text-[#dce85d] bg-[#dce85d]/[0.08] px-1.5 py-0.5 rounded font-semibold">EXECUTE</span>
                      </div>
                      <div className="ml-[18px] space-y-2">
                        <div className="text-xs text-white/70">
                          <span className="text-[#74b97f] font-medium">LONG</span> SOL-PERP · Market order · $420 @ <span className="font-mono text-white/60">$142.38</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="text-[10px] font-mono text-white/20 flex items-center gap-1">
                            <Shield className="w-3 h-3" />
                            SL $138.50
                          </div>
                          <div className="w-px h-3 bg-white/[0.08]" />
                          <div className="text-[10px] font-mono text-white/20 flex items-center gap-1">
                            <TrendingUp className="w-3 h-3" />
                            TP $151.20
                          </div>
                        </div>
                      </div>
                    </motion.div>

                    {/* Entry 5 — Confirmation */}
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: 1.1, ease: [0.25, 1, 0.5, 1] }}
                      className="px-5 py-4"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#74b97f]" />
                        <span className="text-[10px] font-mono text-white/30">00:00:01.342</span>
                        <span className="text-[10px] font-mono text-[#74b97f]/70 bg-[#74b97f]/[0.06] px-1.5 py-0.5 rounded">FILL</span>
                      </div>
                      <div className="ml-[18px] flex items-center justify-between">
                        <div className="text-xs text-white/70">Order filled · tx <span className="font-mono text-white/30">7xKm...3fQp</span></div>
                        <div className="text-[10px] font-mono text-white/20">127ms</div>
                      </div>
                    </motion.div>
                  </div>

                  {/* Terminal footer */}
                  <div className="px-5 py-3 border-t border-white/[0.06] flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-[10px] font-mono text-white/20">bot: RSI-Reversal-v3</span>
                      <span className="w-px h-3 bg-white/[0.06]" />
                      <span className="text-[10px] font-mono text-white/20">runtime: active</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-[#74b97f] animate-pulse" />
                      <span className="text-[10px] font-mono text-white/20">streaming</span>
                    </div>
                  </div>
                </div>

                {/* Ambient glow behind the terminal */}
                <div className="absolute -inset-4 -z-10 rounded-3xl bg-[#dce85d]/[0.02] blur-xl" />
              </motion.div>

            </div>
          </div>
        </section>

        {/* Feature Showcase Grid */}
        <section className="py-24 relative bg-[#090a0a] overflow-hidden">
          <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>

          <div className="max-w-7xl mx-auto px-4 sm:px-8 relative z-10">
            <div className="text-center mb-16 md:mb-24">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5 }}
              >
                <span className="inline-block py-1 px-3 rounded-full bg-white/[0.03] border border-white/[0.08] text-xs font-medium text-white/70 mb-6 uppercase tracking-widest">Platform capabilities</span>
                <h2 className="text-5xl md:text-7xl font-bold text-white tracking-tighter leading-tight mb-6">
                  A social platform for <br className="hidden md:block" />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#dce85d] via-[#a8c93a] to-[#74b97f]">bot creators & copiers</span>
                </h2>
                <p className="text-[#a1a1aa] max-w-2xl mx-auto text-lg md:text-xl font-light">
                  Clone winning strategies, mirror live actions, and customize risk limits seamlessly on-chain.
                </p>
              </motion.div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">

              {/* Left Column (Main Feature) */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: 0.1 }}
                className="lg:col-span-7 flex flex-col"
              >
                <div className="bg-[#121314] relative rounded-[2rem] border border-white/[0.04] p-8 md:p-12 overflow-hidden flex-grow group hover:border-[#dce85d]/30 transition-all duration-700">
                  <div className="absolute right-0 top-0 -mr-24 -mt-24 w-96 h-96 bg-[#dce85d]/10 rounded-full blur-[80px] group-hover:bg-[#dce85d]/20 transition-all duration-700"></div>

                  <div className="relative z-10 flex flex-col h-full">
                    <div className="mb-12">
                      <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.08] mb-6 shadow-inner">
                        <Box className="w-5 h-5 text-[#dce85d]" />
                      </div>
                      <h3 className="text-3xl md:text-4xl font-semibold text-white tracking-tight mb-4">Advanced Bot Builder</h3>
                      <p className="text-[#a1a1aa] text-lg leading-relaxed max-w-md">
                        Harness our visual rules engine to craft precision-driven bots without building complex infrastructure first.
                      </p>
                    </div>

                    <div className="mt-auto relative">
                      {/* Abstract visualization of rules engine */}
                      <div className="bg-black/40 rounded-xl border border-white/[0.06] p-6 backdrop-blur-md">
                        <div className="flex flex-col gap-3">
                          <div className="flex items-center gap-3 w-3/4">
                            <div className="w-2 h-2 rounded-full bg-[#dce85d] shadow-[0_0_10px_#dce85d]"></div>
                            <div className="h-2 rounded-full bg-white/10 flex-grow"></div>
                          </div>
                          <div className="w-px h-6 bg-white/10 ml-[3px]"></div>
                          <div className="flex items-center gap-3 w-full">
                            <div className="w-2 h-2 rounded-full bg-[#a8c93a] shadow-[0_0_10px_#a8c93a]"></div>
                            <div className="h-2 rounded-full bg-white/20 flex-grow"></div>
                            <div className="text-[10px] font-mono text-[#dce85d] bg-[#dce85d]/10 px-2 py-1 rounded">EXECUTE</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>

              {/* Right Column (Sub Features) */}
              <div className="lg:col-span-5 grid grid-rows-2 gap-6">

                {/* Top Right Card */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: 0.2 }}
                >
                  <div className="bg-[#121314] relative rounded-[2rem] border border-white/[0.04] p-8 overflow-hidden h-full group hover:border-[#a8c93a]/30 transition-all duration-700">
                    <div className="absolute left-0 bottom-0 -ml-24 -mb-24 w-64 h-64 bg-[#a8c93a]/10 rounded-full blur-[60px] group-hover:bg-[#a8c93a]/20 transition-all duration-700"></div>

                    <div className="relative z-10 flex gap-6">
                      <div className="flex-shrink-0">
                        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.08] shadow-inner">
                          <TrendingUp className="w-5 h-5 text-[#a8c93a]" />
                        </div>
                      </div>
                      <div>
                        <h3 className="text-xl font-semibold text-white tracking-tight mb-2 group-hover:text-white transition-colors">Creator Marketplace</h3>
                        <p className="text-[#a1a1aa] leading-relaxed">
                          Discover top-performing bots, creator shelves, and transparent on-chain execution with verifiable metrics, then mirror them live.
                        </p>
                        <Link href="/marketplace" className="inline-flex items-center gap-2 mt-4 text-sm font-medium text-[#a8c93a] hover:text-[#dce85d] transition-colors group/link">
                          Open Marketplace
                          <ArrowRight className="w-3.5 h-3.5 group-hover/link:translate-x-1 transition-transform" />
                        </Link>
                      </div>
                    </div>
                  </div>
                </motion.div>

                {/* Bottom Right Card */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: 0.3 }}
                >
                  <div className="bg-[#121314] relative rounded-[2rem] border border-white/[0.04] p-8 overflow-hidden h-full group hover:border-[#74b97f]/30 transition-all duration-700">
                    <div className="absolute right-0 top-1/2 -mr-24 w-64 h-64 bg-[#74b97f]/10 rounded-full blur-[60px] group-hover:bg-[#74b97f]/20 transition-all duration-700"></div>

                    <div className="relative z-10 flex gap-6">
                      <div className="flex-shrink-0">
                        <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.08] shadow-inner">
                          <ShieldCheck className="w-5 h-5 text-[#74b97f]" />
                        </div>
                      </div>
                      <div>
                        <h3 className="text-xl font-semibold text-white tracking-tight mb-2">Delegated Execution</h3>
                        <p className="text-[#a1a1aa] leading-relaxed">
                          Automated trading directly from your self-custody wallet using safe, granular permission controls and advanced risk limits.
                        </p>
                      </div>
                    </div>
                  </div>
                </motion.div>

              </div>
            </div>

            {/* Bottom Platform Features Row */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.4 }}
              className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6"
            >
              {platformFeatures.map((feature, idx) => {
                const Icon = feature.icon;
                return (
                  <div key={idx} className="bg-[#121314] border border-white/[0.04] rounded-2xl p-6 group hover:border-[#dce85d]/20 transition-all duration-300 hover:bg-white/[0.02]">
                    <Icon className="w-5 h-5 text-white/40 group-hover:text-[#dce85d] transition-colors mb-4" />
                    <span className="block text-xs font-mono text-white/40 mb-1">{feature.tag}</span>
                    <span className="block text-sm font-medium text-white">{feature.title}</span>
                  </div>
                );
              })}
            </motion.div>

          </div>
        </section>

        {/* How It Works Section */}
        <section id="how-it-works" className="bg-[#161a1d] py-24 relative">
          <div className="container mx-auto px-4 max-w-3xl">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, ease: [0.25, 1, 0.5, 1] }}
              className="text-center mb-16"
            >
              <h2 className="md:text-6xl text-4xl font-bold text-white tracking-tight mb-4">
                Get Started in <span className="text-[#dce85d]">3 Steps</span>
              </h2>
              <p className="text-lg text-[#a1a1aa]">From zero to earning in minutes</p>
            </motion.div>

            <div className="space-y-4 max-w-2xl mx-auto">
              {steps.map((step, idx) => (
                <motion.div
                  key={step.step}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.45, delay: idx * 0.12, ease: [0.25, 1, 0.5, 1] }}
                  className="glass-card rounded-2xl p-5 transition-all duration-300 hover:scale-[1.02]"
                >
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-[#dce85d] flex items-center justify-center">
                      <span className="text-lg font-bold text-[#090a0a]">{step.step}</span>
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold mb-1 text-white">{step.title}</h3>
                      <p className="text-sm text-[#a1a1aa]">{step.description}</p>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* Community Section */}
        <section className="py-16 lg:py-24 relative bg-[#090a0a]">
          <div className="max-w-7xl mx-auto px-4">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, ease: [0.25, 1, 0.5, 1] }}
              className="flex items-center justify-between mb-8"
            >
              <div>
                <p className="text-xs sm:text-sm text-[#a1a1aa]">What bot authors & followers say</p>
                <h2 className="text-2xl sm:text-3xl md:text-4xl tracking-tight font-semibold text-white">Community</h2>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6, delay: 0.1, ease: [0.25, 1, 0.5, 1] }}
              className="overflow-hidden rounded-3xl bg-[#0a0b0c] border border-white/[0.06] relative"
            >
              <div className="pointer-events-none absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-[#0a0b0c] to-transparent z-10" />
              <div className="pointer-events-none absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-[#0a0b0c] to-transparent z-10" />

              <div className="py-6 relative">
                <div className="flex gap-4 animate-[marqueeLtr_30s_linear_infinite]">
                  {[...duplicatedCommunity.row1, ...duplicatedCommunity.row1].map((t, i) => (
                    <article key={`r1-${i}`} className="shrink-0 w-[280px] sm:w-[360px] rounded-2xl border border-white/[0.08] bg-[#16181a]/40 p-5">
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 rounded-full bg-gradient-to-br ${t.color} flex items-center justify-center text-[#090a0a] font-semibold text-sm`}>{t.initial}</div>
                        <div>
                          <span className="text-sm font-medium text-white block">{t.name}</span>
                          <span className="text-xs text-[#a1a1aa]">{t.handle}</span>
                        </div>
                      </div>
                      <p className="mt-4 text-sm text-[#fafafa]">{t.text}</p>
                    </article>
                  ))}
                </div>
              </div>

              <div className="border-t border-white/[0.08]" />

              <div className="py-6 relative">
                <div className="flex gap-4 animate-[marqueeRtl_30s_linear_infinite]">
                  {[...duplicatedCommunity.row2, ...duplicatedCommunity.row2].map((t, i) => (
                    <article key={`r2-${i}`} className="shrink-0 w-[280px] sm:w-[360px] rounded-2xl border border-white/[0.08] bg-[#16181a]/40 p-5">
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 rounded-full bg-gradient-to-br ${t.color} flex items-center justify-center text-white font-semibold text-sm`}>{t.initial}</div>
                        <div>
                          <span className="text-sm font-medium text-white block">{t.name}</span>
                          <span className="text-xs text-[#a1a1aa]">{t.handle}</span>
                        </div>
                      </div>
                      <p className="mt-4 text-sm text-[#fafafa]">{t.text}</p>
                    </article>
                  ))}
                </div>
              </div>
            </motion.div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-24 relative bg-[#161a1d]">
          <div className="container mx-auto px-4 max-w-4xl">
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 30 }}
              whileInView={{ opacity: 1, scale: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              className="glass-card rounded-3xl p-12 md:p-16 text-center relative overflow-hidden"
            >
              <div className="absolute inset-0 opacity-10">
                <div className="absolute top-0 right-1/4 w-64 h-64 bg-[#dce85d] rounded-full blur-[100px]"></div>
                <div className="absolute bottom-0 left-1/4 w-64 h-64 bg-[#74b97f] rounded-full blur-[100px]"></div>
              </div>
              <div className="relative z-10">
                <motion.h2
                  initial={{ opacity: 0, y: 15 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: 0.15, ease: [0.25, 1, 0.5, 1] }}
                  className="text-4xl md:text-6xl font-bold mb-4 text-white tracking-tight"
                >
                  Ready to <span className="text-[#dce85d]">Maximize</span> Your Tradings?
                </motion.h2>
                <motion.p
                  initial={{ opacity: 0 }}
                  whileInView={{ opacity: 1 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: 0.3 }}
                  className="text-lg text-[#a1a1aa] mb-8 max-w-2xl mx-auto"
                >
                  Join thousands of users who are already earning with ClashX&apos;s automated trading bots
                </motion.p>
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: 0.45, ease: [0.25, 1, 0.5, 1] }}
                >
                  <button type="button" onClick={handleStartBuilding} className="group isolate inline-flex cursor-pointer overflow-hidden transition-all duration-300 hover:scale-105 hover:shadow-[0_0_40px_8px_rgba(220,232,93,0.35)] rounded-full relative shadow-[0_8px_40px_rgba(220,232,93,0.25)]">
                    <div className="absolute inset-0">
                      <div className="absolute inset-[-200%] w-[400%] h-[400%] animate-[rotate-gradient_4s_linear_infinite]">
                        <div className="absolute inset-0" style={{ background: 'conic-gradient(from 225deg, transparent 0, rgba(255,255,255,0.6) 90deg, transparent 90deg)' }}></div>
                      </div>
                    </div>
                    <div className="absolute rounded-full backdrop-blur" style={{ inset: '1px', background: 'rgba(220, 232, 93, 0.1)' }}></div>
                    <div className="z-10 flex gap-3 overflow-hidden text-base font-medium text-white w-full pt-3 pr-5 pb-3 pl-5 relative items-center rounded-full">
                      <div className="absolute inset-[1px] bg-[rgba(10,11,20,0.8)] rounded-full backdrop-blur-[8px]"></div>
                      <span className="whitespace-nowrap relative z-10 font-sans">Launch App</span>
                      <span className="inline-flex items-center justify-center z-10 bg-white/10 w-7 h-7 rounded-full relative"><ArrowRight className="w-4 h-4" /></span>
                    </div>
                  </button>
                </motion.div>
              </div>
            </motion.div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
};

export default Home;
