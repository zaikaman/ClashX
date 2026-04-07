"use client";

import { useEffect, useState } from "react";
import { Joyride, STATUS, Step } from "react-joyride";

const TOUR_STEPS: Step[] = [
  {
    target: "body",
    content: (
      <div className="grid gap-2">
        <h3 className="font-mono text-lg font-bold uppercase text-neutral-50">Welcome to ClashX!</h3>
        <p className="text-sm text-neutral-400">Let's take a quick tour of your new workspace to get you started on building and deploying high-performance trading bots.</p>
      </div>
    ),
    placement: "center",
  },
  {
    target: "[data-tour='wallet-connect']",
    content: (
      <div className="grid gap-2">
        <h3 className="font-mono text-lg font-bold uppercase text-[#dce85d]">Connect Your Wallet</h3>
        <p className="text-sm text-neutral-400">Before deploying bots, you'll need to sign in and connect the wallet ClashX will trade with.</p>
      </div>
    ),
    placement: "bottom",
  },
  {
    target: "[data-tour='nav-builder']",
    content: (
      <div className="grid gap-2">
        <h3 className="font-mono text-lg font-bold uppercase text-[#74b97f]">Builder Studio</h3>
        <p className="text-sm text-neutral-400">Here is where you design and validate your bots using a powerful visual rules engine.</p>
      </div>
    ),
    placement: "right",
  },
  {
    target: "[data-tour='nav-bots']",
    content: (
      <div className="grid gap-2">
        <h3 className="font-mono text-lg font-bold uppercase text-[#a8c93a]">My Bots</h3>
        <p className="text-sm text-neutral-400">Manage all your active and draft bots, monitor performance, and deploy them with a single click.</p>
      </div>
    ),
    placement: "right",
  },
];

export function OnboardingTour() {
  const [run, setRun] = useState(false);

  useEffect(() => {
    // Check if the user has already seen the tour
    const hasSeenTour = localStorage.getItem("clashx-onboarding-completed");
    if (!hasSeenTour) {
      // Delay slightly so the UI can render
      const timer = setTimeout(() => {
        setRun(true);
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleJoyrideCallback = (data: any) => {
    const { status } = data;
    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status as any)) {
      setRun(false);
      localStorage.setItem("clashx-onboarding-completed", "true");
    }
  };

  const JoyrideAny = Joyride as any;

  return (
    <JoyrideAny
      steps={TOUR_STEPS}
      run={run}
      continuous={true}
      scrollToFirstStep={true}
      showProgress={true}
      showSkipButton={true}
      callback={handleJoyrideCallback}
      styles={{
        options: {
          zIndex: 10000,
          primaryColor: "#dce85d",
          backgroundColor: "#16181a",
          textColor: "#f5f5f5",
          arrowColor: "#16181a",
          overlayColor: "rgba(0, 0, 0, 0.75)",
        },
        tooltip: {
          borderRadius: "1rem",
          border: "1px solid rgba(220, 232, 93, 0.2)",
          padding: "20px",
          fontFamily: "inherit",
          boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
        },
        buttonNext: {
          backgroundColor: "#dce85d",
          color: "#090a0a",
          fontWeight: 700,
          textTransform: "uppercase",
          fontSize: "0.75rem",
          letterSpacing: "0.05em",
          borderRadius: "9999px",
          padding: "10px 20px",
        },
        buttonBack: {
          color: "#a1a1aa",
          marginRight: "10px",
          fontSize: "0.75rem",
          textTransform: "uppercase",
          fontWeight: 600,
        },
        buttonSkip: {
          color: "#a1a1aa",
          fontSize: "0.75rem",
          textTransform: "uppercase",
          fontWeight: 600,
        },
        tooltipContainer: {
          textAlign: "left",
        },
        tooltipContent: {
          padding: "10px 0",
        },
      } as any}
    />
  );
}
