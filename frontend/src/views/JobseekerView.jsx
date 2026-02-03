import React, { useState } from 'react';
import { MatchCard } from '../components/MatchCard';
import { SearchableSelect } from '../components/SearchableSelect'; // Import here

export const JobseekerView = ({ users, onMatch, data, isLoading }) => {
  const [selectedUserId, setSelectedUserId] = useState("");

  const handleSelect = (user) => {
    setSelectedUserId(user.youth_id);
    onMatch(user); // Triggers the FastAPI call
  };

  const currentUserMatch = data.find(u => u.user_id === selectedUserId);

  return (
    <div className="space-y-6">
      <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
        <label className="block text-sm font-black text-slate-400 uppercase mb-2 text-indigo-600">
          Search Profile ID
        </label>
        {/* New Searchable Dropdown */}
        <SearchableSelect 
          options={users} 
          onSelect={handleSelect} 
          placeholder="Type to search User ID (e.g. user_001)..."
          labelKey="youth_id"
        />
      </div>

      <div className="grid gap-4">
        {isLoading ? (
          <div className="p-20 text-center animate-pulse text-slate-400 font-black uppercase tracking-tighter">
            AI Engine Calculating...
          </div>
        ) : (
          currentUserMatch?.opportunity_recommendations.map(job => (
            <MatchCard key={job.uuid} job={job} />
          ))
        )}
      </div>
    </div>
  );
};