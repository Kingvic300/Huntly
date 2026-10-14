import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-[var(--radius-control)] font-medium transition-colors disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-[15px] [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-act text-act-ink hover:bg-[#a3b4ff] active:bg-act-strong",
        secondary: "bg-raised text-fg ring-1 ring-inset ring-line hover:bg-hover hover:ring-line-strong",
        ghost: "text-muted hover:bg-raised hover:text-fg",
        danger: "text-bad ring-1 ring-inset ring-bad/35 hover:bg-bad/10",
        link: "h-auto px-0 text-act underline-offset-4 hover:underline",
      },
      size: { sm: "h-7 px-2.5 text-[12.5px]", md: "h-8 px-3 text-[13px]", lg: "h-10 px-4 text-[14px]", icon: "size-8", "icon-sm": "size-7" },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild, loading, children, disabled, ...props }, ref) => {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} disabled={disabled || loading} {...props}>
      {loading ? <Loader2 className="animate-spin" /> : null}
      {children}
    </Comp>
  );
});
Button.displayName = "Button";
