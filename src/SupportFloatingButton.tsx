import { AlertTriangle } from "lucide-react";

type SupportFloatingButtonProps = {
  currentPath: string;
};

function SupportFloatingButton({ currentPath }: SupportFloatingButtonProps) {
  if (currentPath.startsWith("/support")) {
    return null;
  }

  return (
    <a className="support-floating-button" href="/support" aria-label="Reportar error o bug">
      <AlertTriangle size={16} />
      Hubo un error? Reportalo
    </a>
  );
}

export default SupportFloatingButton;

