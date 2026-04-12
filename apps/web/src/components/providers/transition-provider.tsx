"use client";

import { createContext, useContext, useState, ReactNode, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ClashXLogo } from "@/components/clashx-logo";

interface TransitionContextType {
  triggerTransition: (url: string) => void;
}

const TransitionContext = createContext<TransitionContextType | undefined>(undefined);

export function useTransition() {
  const context = useContext(TransitionContext);
  if (!context) {
    throw new Error("useTransition must be used within a TransitionProvider");
  }
  return context;
}

export function TransitionProvider({ children }: { children: ReactNode }) {
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [phase, setPhase] = useState<"idle" | "incoming" | "impact" | "sustaining" | "outgoing">("idle");
  const router = useRouter();
  const pathname = usePathname();

  const triggerTransition = (url: string) => {
    // Prevent triggering if we are already transitioning, or if we are already on the target URL
    if (isTransitioning || pathname === url) return;
    
    setIsTransitioning(true);
    setPhase("incoming");

    // Timeline:
    // 0ms: Walls start flying in
    // 400ms: IMPACT! Walls meet. Screen shake, flash.
    // 400ms - 2400ms: Sustaining (Logo burns in, glows, text appears)
    // 800ms: (Background) Router starts pushing new URL so it loads under the walls
    // 2400ms: Walls start opening (outgoing)
    // 3200ms: Transition completely finished, idle state.

    setTimeout(() => {
      setPhase("impact");
      
      setTimeout(() => {
        setPhase("sustaining");
      }, 100);

      // We trigger the router push slightly after impact so the JS execution doesn't stutter the impact frame
      setTimeout(() => {
        router.push(url);
      }, 400);

      setTimeout(() => {
        setPhase("outgoing");

        setTimeout(() => {
          setPhase("idle");
          setIsTransitioning(false);
        }, 1000);
      }, 2000);
    }, 400);
  };

  return (
    <TransitionContext.Provider value={{ triggerTransition }}>
      {children}
      <AnimatePresence>
        {isTransitioning && (
          <div className="fixed inset-0 z-[99999] pointer-events-none flex items-center justify-center overflow-hidden">
            
            {/* Dark overlay that fades in rapidly to hide the current page just before walls connect */}
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: phase === "incoming" ? 0 : 1 }}
              transition={{ duration: 0.1 }}
              className="absolute inset-0 bg-[#040404] z-0"
            />

            {/* Global Screen Shake Container for the Impact */}
            <motion.div
              animate={
                phase === "impact" ? { x: [-10, 10, -10, 10, -5, 5, 0], y: [-10, 10, -5, 5, -2, 2, 0] } : { x: 0, y: 0 }
              }
              transition={{ duration: 0.4, ease: "easeOut" }}
              className="absolute inset-0 flex items-center justify-center z-10"
            >
              {/* TOP WALL (Changed from Left/Right to Top/Bottom for a heavier blast door feel) */}
              <motion.div
                initial={{ y: "-100%" }}
                animate={
                  phase === "incoming" ? { y: "-100%" } : 
                  phase === "outgoing" ? { y: "-100%" } : 
                  { y: "0%" }
                }
                transition={{
                  duration: phase === "outgoing" ? 0.8 : 0.4,
                  ease: phase === "outgoing" ? [0.76, 0, 0.24, 1] : [0.8, 0, 1, 1], // Slam in, ease out
                }}
                className="absolute top-0 left-0 right-0 h-1/2 bg-[#090a0a] border-b-[3px] border-[#dce85d] shadow-[0_10px_50px_rgba(220,232,93,0.15)] flex items-end justify-center overflow-hidden"
              >
                {/* Texture/Grime on the wall */}
                <div className="absolute inset-0 opacity-20 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] mix-blend-overlay"></div>
              </motion.div>
              
              {/* BOTTOM WALL */}
              <motion.div
                initial={{ y: "100%" }}
                animate={
                  phase === "incoming" ? { y: "100%" } : 
                  phase === "outgoing" ? { y: "100%" } : 
                  { y: "0%" }
                }
                transition={{
                  duration: phase === "outgoing" ? 0.8 : 0.4,
                  ease: phase === "outgoing" ? [0.76, 0, 0.24, 1] : [0.8, 0, 1, 1],
                }}
                className="absolute bottom-0 left-0 right-0 h-1/2 bg-[#090a0a] border-t-[3px] border-[#dce85d] shadow-[0_-10px_50px_rgba(220,232,93,0.15)] flex items-start justify-center overflow-hidden"
              >
                <div className="absolute inset-0 opacity-20 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] mix-blend-overlay"></div>
              </motion.div>

              {/* Central Impact Flash */}
              <AnimatePresence>
                {phase === "impact" && (
                  <motion.div
                    initial={{ scaleY: 0, opacity: 0.8, height: "2px", width: "100vw" }}
                    animate={{ scaleY: [1, 50, 0], opacity: [1, 1, 0] }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                    className="absolute z-20 bg-white shadow-[0_0_100px_20px_#dce85d]"
                  />
                )}
              </AnimatePresence>

              {/* Logo & Typography container (Revealed after impact) */}
              <AnimatePresence>
                {(phase === "impact" || phase === "sustaining") && (
                  <motion.div
                    initial={{ scale: 1.2, opacity: 0, filter: "blur(10px) brightness(2)" }}
                    animate={{ scale: 1, opacity: 1, filter: "blur(0px) brightness(1)" }}
                    exit={{ scale: 0.9, opacity: 0, filter: "blur(5px)" }}
                    transition={{ 
                      type: "spring", stiffness: 200, damping: 20,
                      opacity: { duration: 0.2 },
                      filter: { duration: 0.4 }
                    }}
                    className="absolute z-30 flex flex-col items-center justify-center gap-6 mix-blend-lighten"
                  >
                    {/* Glowing Aura behind logo */}
                    <motion.div 
                      animate={{ 
                        scale: [1, 1.2, 1],
                        opacity: [0.3, 0.6, 0.3]
                      }}
                      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                      className="absolute inset-0 bg-[#dce85d] w-[200%] h-[200%] -left-1/2 -top-1/2 rounded-full blur-[80px] -z-10 pointer-events-none"
                    />

                    <div className="flex items-center gap-5">
                      <motion.div
                        initial={{ rotate: -90, scale: 0 }}
                        animate={{ rotate: 0, scale: 1 }}
                        transition={{ type: "spring", bounce: 0.5, duration: 0.8, delay: 0.1 }}
                      >
                        <ClashXLogo className="w-24 h-24 text-white drop-shadow-[0_0_15px_rgba(255,255,255,0.5)]" />
                      </motion.div>
                      
                      <div className="flex flex-col items-start justify-center">
                        <div className="flex font-black tracking-tighter text-8xl uppercase leading-none overflow-hidden">
                          <motion.span 
                            initial={{ y: "100%" }}
                            animate={{ y: "0%" }}
                            transition={{ type: "spring", bounce: 0, duration: 0.6, delay: 0.2 }}
                            className="text-white"
                          >
                            Clash
                          </motion.span>
                          <motion.span 
                            initial={{ x: -20, opacity: 0, scale: 0.8 }}
                            animate={{ x: 0, opacity: 1, scale: 1 }}
                            transition={{ type: "spring", bounce: 0.6, duration: 0.6, delay: 0.4 }}
                            className="text-[#dce85d] ml-[2px] drop-shadow-[0_0_20px_rgba(220,232,93,0.5)]"
                          >
                            X
                          </motion.span>
                        </div>
                      </div>
                    </div>

                    <motion.div 
                      initial={{ opacity: 0, letterSpacing: "1em" }}
                      animate={{ opacity: 1, letterSpacing: "0.4em" }}
                      transition={{ duration: 1, delay: 0.5, ease: "easeOut" }}
                      className="text-[#a0a0a0] text-sm font-bold uppercase"
                    >
                      Enter The Arena
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>

            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </TransitionContext.Provider>
  );
}