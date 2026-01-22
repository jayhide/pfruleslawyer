interface UserMessageProps {
  content: string;
}

export function UserMessage({ content }: UserMessageProps) {
  return (
    <div className="flex justify-end mb-4">
      <div className="max-w-[80%] bg-primary-600 text-white rounded-2xl rounded-br-md px-4 py-3">
        <p className="whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
