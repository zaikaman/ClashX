"use client";

import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';
import Script from 'next/script';
import {
  ArrowRight, Shield, Zap, TrendingUp, Box, Users,
  Activity, ShieldCheck, Layers, Sparkles, Menu, X,
  Github, Twitter, Send, FileText, BookOpen
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { ClashXLogo } from '@/components/clashx-logo';

const LandingHeader = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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
            <Link href="/build" className="group relative inline-flex items-center justify-center h-[38px] px-5 gap-2 text-sm font-semibold text-[#090a0a] bg-[#dce85d] rounded-full overflow-hidden transition-all duration-300 ease-out hover:scale-105 hover:bg-[#e4ef6e] focus:outline-none focus:ring-2 focus:ring-[#dce85d] focus:ring-offset-2 focus:ring-offset-[#090a0a]">
              <span className="relative z-10 flex items-center gap-1.5 whitespace-nowrap">
                Start Building
                <ArrowRight className="w-3.5 h-3.5 transition-transform duration-300 group-hover:translate-x-0.5" />
              </span>
              <div className="absolute inset-0 z-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out rounded-full shadow-[inset_0_1px_1px_rgba(255,255,255,0.4)]"></div>
            </Link>
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
                  <Link href="/build" className="w-full group isolate inline-flex justify-center cursor-pointer overflow-hidden transition-all duration-300 hover:scale-[1.02] hover:shadow-[0_0_40px_8px_rgba(220,232,93,0.35)] rounded-full relative shadow-[0_8px_40px_rgba(220,232,93,0.25)] h-12">
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
                  </Link>
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
  const [isMobile, setIsMobile] = useState(false);
  const [isFeaturesSectionVisible, setIsFeaturesSectionVisible] = useState(false);


  useEffect(() => {
    // The animated background is decorative, so it can load after the route is interactive.
    const initUnicorn = () => {
      const UnicornStudio = (window as any).UnicornStudio;
      if (UnicornStudio) {
        try {
          UnicornStudio.init();
        } catch (error) {
          console.error('Error initializing UnicornStudio:', error);
        }
      }
    };

    // Check if already loaded
    if ((window as any).UnicornStudio) {
      initUnicorn();
    } else {
      const unicornScript = document.querySelector<HTMLScriptElement>('script[src="/unicornStudio.umd.js"]');
      if (!unicornScript) {
        return;
      }
      unicornScript.addEventListener('load', initUnicorn, { once: true });
      return () => unicornScript.removeEventListener('load', initUnicorn);
    }
  }, []);


  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.target.id === 'features') {
            setIsFeaturesSectionVisible(entry.isIntersecting);
          }
        });
      },
      { threshold: 0.1 }
    );

    const featuresSection = document.getElementById('features');
    if (featuresSection) observer.observe(featuresSection);

    return () => {
      if (featuresSection) observer.unobserve(featuresSection);
    };
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
      text: 'Cloning the top leaderboard bot transformed my trading. The copy limits keep me perfectly safe.',
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
      <Script src="/unicornStudio.umd.js" strategy="lazyOnload" />
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
                  <Link href="/build" className="group isolate inline-flex cursor-pointer overflow-hidden transition-all duration-300 hover:scale-105 hover:shadow-[0_0_40px_8px_rgba(220,232,93,0.35)] rounded-full relative shadow-[0_8px_40px_rgba(220,232,93,0.25)]">
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
                  </Link>
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, duration: 0.3 }}
                className="grid grid-cols-2 md:grid-cols-4 gap-3"
              >
                {stats.map((stat) => {
                  const Icon = stat.icon;
                  return (
                    <div key={stat.label} className="p-4 text-center bg-card rounded-xl border border-white/[0.06] hover:border-[#dce85d]/30 transition-colors">
                      <div className="flex items-center justify-center gap-2 mb-2">
                        <Icon className="w-4 h-4 text-[#dce85d]" />
                        <div className="text-2xl font-bold text-neutral-50">{stat.value}</div>
                      </div>
                      <div className="text-xs text-neutral-400 mb-1">{stat.label}</div>
                      <div className="text-xs text-[#74b97f] font-medium">{stat.change}</div>
                    </div>
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

        {/* Features Section */}
        <section id="features" className="py-24 relative bg-[#090a0a] overflow-hidden">
          <div className="opacity-30 absolute top-0 right-0 bottom-0 left-0 will-change-[filter] transform-gpu">
            <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-[#dce85d] rounded-full blur-[60px] md:blur-[120px]"></div>
            <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-[#74b97f] rounded-full blur-[60px] md:blur-[120px]"></div>
          </div>

          <div className="container mx-auto px-4 max-w-7xl relative z-10">
            <div className="text-center mb-16">
              <span className="inline-flex items-center gap-2 rounded-full bg-[#dce85d]/10 px-3 py-1.5 text-xs text-[#dce85d] ring-1 ring-[#dce85d]/20 uppercase tracking-tight mb-4">
                <Sparkles className="w-3.5 h-3.5" />
                Platform Features
              </span>
              <h2 className="text-4xl md:text-6xl font-bold mb-4 text-white tracking-tight">
                Everything You Need to{' '}
                <span className="text-[#dce85d]">Succeed</span>
              </h2>
              <p className="text-lg text-[#a1a1aa] max-w-2xl mx-auto">
                Powerful tools and integrations designed to maximize your trading bots
              </p>
            </div>

            <div className="relative mx-auto mt-12 max-w-5xl mb-16">
              <div className="flex gap-8 sm:gap-12 mb-8 items-center justify-center flex-wrap">
                {[Shield, Activity, Box, Layers, TrendingUp, Zap].map((Icon, idx) => (
                  <motion.span
                    key={idx}
                    whileHover={{ scale: 1.1 }}
                    className="inline-flex items-center justify-center glass-card w-14 h-14 rounded-xl will-change-transform"
                    style={{ animation: isFeaturesSectionVisible ? `float 3s ease-in-out infinite ${idx * 0.2}s` : 'none' }}
                  >
                    <Icon className="w-6 h-6 text-[#dce85d]" />
                  </motion.span>
                ))}
              </div>

              <div className="relative h-72 hidden md:block">
                <svg viewBox="0 0 900 360" className="absolute inset-0 w-full h-full max-w-[1008px] mx-auto will-change-transform transform-gpu" fill="none" strokeWidth="2">
                  <defs>
                    <filter id="glow">
                      <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                      <feMerge>
                        <feMergeNode in="coloredBlur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>

                  {[150, 270, 390, 510, 630, 750].map((cx, idx) => (
                    <circle key={idx} cx={cx} cy="30" r="5" fill="#dce85d" filter="url(#glow)" style={{ animation: `pulse-glow 2s ease-in-out infinite ${idx * 0.2}s` }} />
                  ))}

                  <path d="M450 300 C 450 200, 300 120, 150 30" stroke="#dce85d" strokeWidth="2" strokeLinecap="round" opacity="0.6">
                    <animate attributeName="stroke-dashoffset" values="600;0;600" dur="3s" repeatCount="indefinite" />
                  </path>
                  <path d="M450 300 C 450 210, 360 130, 270 30" stroke="#dce85d" strokeWidth="2" strokeLinecap="round" opacity="0.6">
                    <animate attributeName="stroke-dashoffset" values="520;0;520" dur="3s" begin="0.2s" repeatCount="indefinite" />
                  </path>
                  <path d="M450 300 C 450 150, 420 80, 390 30" stroke="#dce85d" strokeWidth="2" strokeLinecap="round" opacity="0.6">
                    <animate attributeName="stroke-dashoffset" values="450;0;450" dur="3s" begin="0.4s" repeatCount="indefinite" />
                  </path>
                  <path d="M450 300 C 450 150, 480 80, 510 30" stroke="#dce85d" strokeWidth="2" strokeLinecap="round" opacity="0.6">
                    <animate attributeName="stroke-dashoffset" values="450;0;450" dur="3s" begin="0.6s" repeatCount="indefinite" />
                  </path>
                  <path d="M450 300 C 450 210, 540 130, 630 30" stroke="#dce85d" strokeWidth="2" strokeLinecap="round" opacity="0.6">
                    <animate attributeName="stroke-dashoffset" values="520;0;520" dur="3s" begin="0.8s" repeatCount="indefinite" />
                  </path>
                  <path d="M450 300 C 450 200, 600 120, 750 30" stroke="#dce85d" strokeWidth="2" strokeLinecap="round" opacity="0.6">
                    <animate attributeName="stroke-dashoffset" values="600;0;600" dur="3s" begin="1s" repeatCount="indefinite" />
                  </path>
                </svg>

                <div className="absolute bottom-4 left-1/2 -translate-x-1/2">
                  <span className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-[#dce85d]/20 ring-2 ring-[#dce85d]/40 shadow-[0_0_30px_rgba(220,232,93,0.6)]">
                    <Sparkles className="w-8 h-8 text-[#dce85d]" />
                  </span>
                </div>
              </div>
            </div>

            <div className="mx-auto max-w-5xl mt-16">
              <div className="flex flex-wrap md:flex-nowrap text-sm gap-x-4 gap-y-4 items-center justify-center">
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass-card whitespace-nowrap">
                  <ShieldCheck className="w-4 h-4 text-[#dce85d]" />
                  <span className="text-neutral-50">Audited Smart Contracts</span>
                </div>
                <div className="hidden md:block w-16 h-px border-t border-dashed border-[#dce85d]/40"></div>
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass-card whitespace-nowrap">
                  <Activity className="w-4 h-4 text-[#dce85d]" />
                  <span className="text-neutral-50">Real-time Monitoring</span>
                </div>
                <div className="hidden md:block w-16 h-px border-t border-dashed border-[#dce85d]/40"></div>
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass-card whitespace-nowrap">
                  <Layers className="w-4 h-4 text-[#dce85d]" />
                  <span className="text-neutral-50">Multi-Protocol Support</span>
                </div>
                <div className="hidden md:block w-16 h-px border-t border-dashed border-[#dce85d]/40"></div>
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass-card whitespace-nowrap">
                  <Sparkles className="w-4 h-4 text-[#dce85d]" />
                  <span className="text-neutral-50">AI-Powered Optimization</span>
                </div>
              </div>
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
                        <h3 className="text-xl font-semibold text-white tracking-tight mb-2 group-hover:text-white transition-colors">Public Leaderboards</h3>
                        <p className="text-[#a1a1aa] leading-relaxed">
                          Discover top-performing bots. Analyze their historical performance and transparent on-chain execution with verifiable metrics, then mirror them live.
                        </p>
                        <Link href="/leaderboard" className="inline-flex items-center gap-2 mt-4 text-sm font-medium text-[#a8c93a] hover:text-[#dce85d] transition-colors group/link">
                          View Leaderboards
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
            <div className="text-center mb-16">
              <h2 className="md:text-6xl text-4xl font-bold text-white tracking-tight mb-4">
                Get Started in <span className="text-[#dce85d]">3 Steps</span>
              </h2>
              <p className="text-lg text-[#a1a1aa]">From zero to earning in minutes</p>
            </div>

            <div className="space-y-4 max-w-2xl mx-auto">
              {steps.map((step) => (
                <div key={step.step} className="glass-card rounded-2xl p-5 transition-all duration-300 hover:scale-[1.02]">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-[#dce85d] flex items-center justify-center">
                      <span className="text-lg font-bold text-[#090a0a]">{step.step}</span>
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold mb-1 text-white">{step.title}</h3>
                      <p className="text-sm text-[#a1a1aa]">{step.description}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Community Section */}
        <section className="py-16 lg:py-24 relative bg-[#090a0a]">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex items-center justify-between mb-8">
              <div>
                <p className="text-xs sm:text-sm text-[#a1a1aa]">What bot authors & followers say</p>
                <h2 className="text-2xl sm:text-3xl md:text-4xl tracking-tight font-semibold text-white">Community</h2>
              </div>
            </div>

            <div className="overflow-hidden rounded-3xl bg-[#0a0b0c] border border-white/[0.06] relative">
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
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-24 relative bg-[#161a1d]">
          <div className="container mx-auto px-4 max-w-4xl">
            <div className="glass-card rounded-3xl p-12 md:p-16 text-center relative overflow-hidden">
              <div className="absolute inset-0 opacity-10">
                <div className="absolute top-0 right-1/4 w-64 h-64 bg-[#dce85d] rounded-full blur-[100px]"></div>
                <div className="absolute bottom-0 left-1/4 w-64 h-64 bg-[#74b97f] rounded-full blur-[100px]"></div>
              </div>
              <div className="relative z-10">
                <h2 className="text-4xl md:text-6xl font-bold mb-4 text-white tracking-tight">
                  Ready to <span className="text-[#dce85d]">Maximize</span> Your Tradings?
                </h2>
                <p className="text-lg text-[#a1a1aa] mb-8 max-w-2xl mx-auto">
                  Join thousands of users who are already earning with ClashX&apos;s automated trading bots
                </p>
                <Link href="/build" className="group isolate inline-flex cursor-pointer overflow-hidden transition-all duration-300 hover:scale-105 hover:shadow-[0_0_40px_8px_rgba(220,232,93,0.35)] rounded-full relative shadow-[0_8px_40px_rgba(220,232,93,0.25)]">
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
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
};

export default Home;
