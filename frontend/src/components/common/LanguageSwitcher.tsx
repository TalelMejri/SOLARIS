import { Button } from "@/components/ui/button";
import { LanguageContext } from "@/i18n";
import { useContext, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Globe, Check } from "lucide-react";

const languages = [
    { value: "fr", label: "Français", flag: "🇫🇷", color: "text-blue-500" },
    { value: "en", label: "English", flag: "🇺🇸", color: "text-red-500" },
];

export function LanguageSwitcher() {
    const { language: currentLanguage, setLanguage } = useContext(LanguageContext);
    const [showLanguageDropdown, setShowLanguageDropdown] = useState(false);

    const currentLanguageInfo =
        languages.find((lang) => lang.value === currentLanguage) || languages[0];

    const changeLanguage = (lng: string) => {
        setLanguage(lng);
        setShowLanguageDropdown(false);

        // Ripple effect
        const button = document.querySelector(
            `[data-language="${lng}"]`
        ) as HTMLElement | null;
        if (button) {
            const ripple = document.createElement("span");
            ripple.style.cssText = `
        position: absolute;
        border-radius: 50%;
        background: var(--primary);
        transform: scale(0);
        animation: ripple 0.6s linear;
        pointer-events: none;
      `;
            const rect = button.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            ripple.style.width = ripple.style.height = `${size}px`;
            ripple.style.left = `${rect.width / 2 - size / 2}px`;
            ripple.style.top = `${rect.height / 2 - size / 2}px`;
            button.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        }
    };

    return (
        <div className="relative inline-block">
            <Button
                onClick={() => setShowLanguageDropdown((v) => !v)}
                className="bg-background/80 backdrop-blur-xl border border-border/50 rounded-2xl shadow-2xl px-4 py-3 gap-2"
            >
                <Globe className="w-4 h-4 text-primary" />
                <span className="font-semibold text-foreground">
                    {currentLanguageInfo.value.toUpperCase()}
                </span>
                <ChevronDown className="w-3 h-3 text-muted-foreground" />
            </Button>

            <AnimatePresence>
                {showLanguageDropdown && (
                    <motion.div
                        initial={{ opacity: 0, y: -10, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -10, scale: 0.95 }}
                        transition={{ duration: 0.2, type: "spring" }}
                        className="absolute top-full mt-3 right-0 bg-background/95 backdrop-blur-xl border border-border/50 rounded-xl shadow-2xl py-2 z-50 min-w-35 overflow-hidden"
                    >
                        <div className="absolute inset-0 bg-linear-to-b from-transparent via-primary/5 to-transparent pointer-events-none" />
                        {languages.map((language, index) => (
                            <motion.button
                                key={language.value}
                                data-language={language.value}
                                onClick={() => changeLanguage(language.value)}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.05 }}
                                className={`relative flex items-center justify-between w-full px-4 py-2.5 transition-all duration-200 group/language overflow-hidden ${currentLanguage === language.value
                                    ? "bg-primary/20 text-primary"
                                    : "text-foreground hover:bg-accent/30"
                                    }`}
                            >
                                <div className="absolute inset-0 bg-linear-to-r from-transparent via-primary/5 to-transparent opacity-0 group-hover/language:opacity-100 transition-opacity duration-300" />
                                <div className="relative z-10 flex items-center gap-3">
                                    <span className="text-lg">{language.flag}</span>
                                    <span className="font-medium text-sm">{language.label}</span>
                                </div>
                                {currentLanguage === language.value && (
                                    <motion.div
                                        initial={{ scale: 0 }}
                                        animate={{ scale: 1 }}
                                        transition={{ type: "spring" }}
                                        className="relative z-10"
                                    >
                                        <Check className="w-4 h-4 text-primary" />
                                    </motion.div>
                                )}
                            </motion.button>
                        ))}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}