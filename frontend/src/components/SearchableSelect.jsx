import React, { useState } from 'react';

export const SearchableSelect = ({ options, onSelect, placeholder, labelKey = "id" }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  // Filter options based on typing
  const filteredOptions = options.filter(option => 
    option[labelKey].toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="relative w-full">
      <input
        type="text"
        placeholder={placeholder}
        className="w-full bg-slate-50 border border-slate-200 p-3 rounded-xl font-bold text-slate-700 outline-none focus:ring-2 ring-indigo-500 transition-all"
        value={searchTerm}
        onChange={(e) => {
          setSearchTerm(e.target.value);
          setIsOpen(true);
        }}
        onFocus={() => setIsOpen(true)}
      />
      
      {isOpen && searchTerm && (
        <div className="absolute z-50 w-full mt-2 bg-white border border-slate-200 rounded-xl shadow-xl max-h-60 overflow-y-auto">
          {filteredOptions.length > 0 ? (
            filteredOptions.map((option, index) => (
              <div
                key={index}
                className="p-3 hover:bg-indigo-50 cursor-pointer font-bold text-slate-600 border-b border-slate-50 last:border-none"
                onClick={() => {
                  onSelect(option);
                  setSearchTerm(option[labelKey]);
                  setIsOpen(false);
                }}
              >
                {option[labelKey]}
              </div>
            ))
          ) : (
            <div className="p-3 text-slate-400 italic">No matches found</div>
          )}
        </div>
      )}
    </div>
  );
};