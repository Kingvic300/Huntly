import * as DM from "@radix-ui/react-dropdown-menu";
import * as React from "react";
import { cn } from "@/lib/utils";

export const DropdownMenu = DM.Root;
export const DropdownMenuTrigger = DM.Trigger;

export function DropdownMenuContent({ className, align = "end", ...props }: React.ComponentProps<typeof DM.Content>) {
  return (
    <DM.Portal>
      <DM.Content align={align} sideOffset={6} className={cn("z-50 min-w-52 rounded-[10px] bg-raised p-1 ring-1 ring-line-strong", className)} {...props} />
    </DM.Portal>
  );
}

export function DropdownMenuItem({ className, ...props }: React.ComponentProps<typeof DM.Item>) {
  return (
    <DM.Item
      className={cn(
        "flex cursor-default items-center gap-2.5 rounded-[6px] px-2 py-1.5 text-[13px] text-fg outline-none data-[highlighted]:bg-hover data-[disabled]:opacity-45 [&_svg]:size-[15px] [&_svg]:text-muted",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuLabel({ className, ...props }: React.ComponentProps<typeof DM.Label>) {
  return <DM.Label className={cn("px-2 py-1.5 text-[12.5px] text-muted", className)} {...props} />;
}

export function DropdownMenuSeparator() {
  return <DM.Separator className="mx-1 my-1 h-px bg-line" />;
}
